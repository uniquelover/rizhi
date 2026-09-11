import os.path
import serial
import time
from log_tool.gdata import Gdata
import threading
from video.video_util import func_record
from video.video_util import CameraRecorder
from airtest.core.android.adb import ADB
class SerialHandler:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.serial = serial.Serial(port, baudrate, timeout=1)

    def open_serial(self):
        """打开串口"""
        self.serial.open()

    def close_serial(self):
        """关闭串口"""
        self.serial.close()

    def read_data(self):
        """读取串口数据"""
        if self.serial.is_open:
            return self.serial.readline().decode('utf-8').strip()
        else:
            return None

    def write_data(self, data):
        """向串口写入数据"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        elif isinstance(data, bytes):
            pass
        else:
            print(data)
            raise Exception(f"写串口遇到异常数据类型")
        if self.serial.is_open:
            self.serial.write(data)
        else:
            print("Serial port is not open.")

    def build_data(self, address, open_switch):

        def calc_checksum(start, addr, cmd):
            """简单加和校验"""
            return (start + addr + cmd) & 0xFF

        start_flag = 0xA0
        address = address
        cmd = 0x01 if open_switch else 0x00
        checksum = calc_checksum(start_flag, address, cmd)
        data = bytes([start_flag, address, cmd, checksum])
        return data

    def check_str(self, info):
        """检查是否出现特定的字符串"""
        buffer = ""  # 用于拼接数据的缓冲区
        info_len = len(info)
        is_find = False
        t1 = time.time()
        while True:
            if time.time() - t1 > 60:
                break  # 超时控制
            data = self.read_data()
            with open('log.txt', 'a') as flog:
                if data and data.strip():
                    flog.write(data+'\n')
            if data is not None and data.strip():
                buffer += data  # 将新读取到的数据拼接到缓冲区
                # 检测目标字符串
                if info in buffer:
                    print(f" detected: {buffer}")
                    is_find = True
                    break
                else:
                    buffer = buffer[-info_len:]  # 保留最近3个字符，确保不会错过目标字符串
        return is_find

def serial_ign_acc(handler, state):
    # state True 代表打开
    data = handler.build_data(0X01, state)
    handler.write_data(data)


def convert_seconds_to_hms(seconds):
    """
    将秒数转换为时分秒格式的字符串
    :param seconds: 秒数
    :return: 时分秒格式的字符串
    """
    hours = seconds // 3600  # 计算小时数
    minutes = (seconds % 3600) // 60  # 计算分钟数
    seconds = seconds % 60  # 计算剩余秒数
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"  # 格式化输出，补零


if __name__ == "__main__":
    # 串口配置
    import sys

    camera=None
    if len(sys.argv)>1:
        camera=int(sys.argv[1])
    from utils.yaml_util import YamlRead
    yml_file = f'config.yml'
    yamlobj = YamlRead(yml_file)
    config_data = yamlobj.read_data()  # 没有作为实例变量
    port_relay=config_data['port_relay']
    port_qnx=config_data['port_qnx']
    monkey_time=int(config_data['monkey_time'])
    print(f'port_relay:{port_relay},port_qnx:{port_qnx},monkey_time:{monkey_time} ')

    port =port_relay # 'COM6'  # Windows示例
    baudrate = 9600
    handler_relay = SerialHandler(port, baudrate)

    port = port_qnx  #'COM8'  # Windows示例
    baudrate = 115200
    handler_qnx = SerialHandler(port, baudrate)

    if os.path.exists('result.csv'):
        os.remove('result.csv')
    if os.path.exists('log.txt'):
        os.remove('log.txt')
    with open('result.csv', 'a') as fre:
        fre.write(f'"轮次","进入str","退出str","视频时刻"\n')
    loop = 0
    mcamera = CameraRecorder(camera_index=camera)
    producer_thread = threading.Thread(target=func_record, args=(mcamera,)) #frame_queue
    producer_thread.start()
    print('## start camera')
    try:
        while True:
            loop += 1
            serial_ign_acc(handler_relay, False)
            print('close switch')
            res = handler_qnx.check_str('ENTER STR end', )  # 进入str

            with open('result.csv', 'a') as fre:
                t1=convert_seconds_to_hms(int(time.time()-Gdata.record_start))
                fre.write(f'{loop},{res},"",{t1}\n')
            print(f'%%check ENTER STR end:{res}')
            if not res:
                print('!! 进入 str 异常')
                # break

            serial_ign_acc(handler_relay, True)
            print('open switch')
            res = handler_qnx.check_str('Wakeup from STR', )  # 进入str  Wakeup from STR
            with open('result.csv', 'a') as fre:
                t1=convert_seconds_to_hms(int(time.time()-Gdata.record_start))
                fre.write(f'{loop},"",{res},{t1}\n')
            if not res:
                print('!! 退出 str 异常')
                # break

            print('wait 5')
            time.sleep(5)
            from press_android.monkey import start_monkey_thread,stop_monkey
            start_monkey_thread()
            time.sleep(monkey_time)
            stop_monkey()
            print(f'%%check Wakeup from STR:{res}')
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，即将进入后处理函数。")
        # post_processing()
        time.sleep(30)
        mcamera.stop_recording()
        print('stop recording')

    # time.sleep(30)
    # mcamera.stop_recording()
    # print('stop recording')

