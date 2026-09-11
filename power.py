# import pyvisa
# from airtest.core.helper import G
import sys
# from PyQt5.QtWidgets import *
# from PyQt5.QtCore import pyqtSignal, Qt
import time
# from zlgsendcan.parseDBC import GlobleValue
# from utils.camera_util import judge_mode

# class DialogPower(QDialog):
#     dialogSignel = pyqtSignal(bool, str, str)  # bool 对应本次对话是否撤销
#     def __init__(self, parent=None):
#         super(DialogPower, self).__init__(parent)
#         layout = QVBoxLayout()

#         hlayout = QHBoxLayout()
#         le = QLabel('设置电压(V)')
#         hlayout.addWidget(le)
#         self.power_value = QLineEdit("", )
#         hlayout.addWidget(self.power_value)
#         layout.addLayout(hlayout)

#         hlayout = QHBoxLayout()
#         le = QLabel('设置电流(A 默认5A)')
#         hlayout.addWidget(le)
#         self.current_value = QLineEdit("", )
#         hlayout.addWidget(self.current_value)
#         layout.addLayout(hlayout)

#         buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
#         buttons.accepted.connect(self.accept)  # 点击ok
#         buttons.rejected.connect(self.reject)  # 点击cancel
#         layout.addWidget(buttons)

#         self.setLayout(layout)
#         self.setWindowTitle('可编程电源')

#     def accept(self):  # 点击ok是发送内置信号
#         power_value = self.power_value.text()
#         current_value = self.current_value.text()
#         self.dialogSignel.emit(True, power_value, current_value)
#         self.destroy()

#     def reject(self):  # 点击cancel时，发送自定义信号
#         self.dialogSignel.emit(False, '', '')
#         self.destroy()


def power_set(vol=None, curr=None, state='on', project='tlp国际'):
    """
    vol 电压
    curr 电流
    state 状态 On:打开   off:关闭
    """

    rm = pyvisa.ResourceManager()
    try:
        device_list = rm.list_resources()
        if len(device_list) > 0:
            device = device_list[0]
        else:
            G.LOGGER.log_db("no powersupply device found")
    except Exception as e:
        G.LOGGER.log_db('PowerSupply device get some error')
        G.LOGGER.log_db(e)
        sys.exit(0)

    my_device = rm.open_resource(device)  # 打开仪器连接


    # my_device.baud_rate = 9600        # 波特率
    # my_device.data_bits = 8           # 数据位
    # my_device.parity = pyvisa.constants.Parity.none  # 校验位
    # my_device.stop_bits = pyvisa.constants.StopBits.one  # 停止位
    # my_device.write_termination = '\r\n'  # 写入终止符
    # my_device.read_termination = '\r\n'   # 读取终止符


    # voltage = 9.0
    # my_device.write(f"VOLT {voltage}")
    # print(f"已将输出电压设置为{voltage}V")
    # time.sleep(2)
    # max_retries = 3
    # retry_count = 0
    # while retry_count < max_retries:
    #     try:
    #         current_voltage = my_device.query('MEAS:VOLT?')
    #         print(f"当前设置的电压:{current_voltage.strip()}V")
    #         break
    #     except pyvisa.errors.VisaIOError as e:
    #         retry_count += 1
    #         if retry_count < max_retries:
    #             print(f"查询仪器标识信息时发生超时错误(第{retry_count}次重试):{e}")
    #         else:
    #            print(f"查询仪器标识信息时发生超时错误,已达到最大重试次数:{e}")

        # finally:
        #     my_device.close()
    # try:
    #     data = my_device.read()
    # except pyvisa.errors.VisaIOError as e:
    #     print(f"Error code: {e.error_code}, Message: {e}")
    #     if e.error_code == -1073807339:  # VI_ERROR_TMO
    #         print("Timeout error occurred.")
    #     else:
    #         raise
    # my_device.write('*IDN?')
    # try:
    #     supported_commands = my_device.query("*LRN?")
    #     print("仪器支持的命令:", supported_commands)
    # except pyvisa.errors.VisaIOError:
    #     print("仪器不支持 *LRN? 命令，请查阅仪器手册获取支持的命令。")
    # my_device.timeout = 5000
    if str(vol).strip():
        
        out = my_device.write("VOLTage %s" % vol)
        print(f"设置电压为{vol}V")
    
    # if str(curr).strip():
    #     print("设置电流")
    #     my_device.write("CURRent %s" % curr)

       
    my_device.write("OUTP %s" % state)

    # my_device.close()
    # output_status = my_device.query("OUTP?")
    # print(f"电源输出状态: {output_status.strip()}")

    # 这里电压的切换和项目结合到一起
    # if project == 'tlp国际' and (9 <= vol <= 16):
    #     start = time.time()
    #     while True:
    #         if time.time() - start > 80: #yh
    #             print('*** timeout  not find d1_d2')
    #             break
    #         if judge_mode(ratio_value=GlobleValue.ratio_pic) == 'pass':
    #             print('*** find d1_d2')
    #             break
    #         time.sleep(0.1)



if __name__ == '__main__':

    from serial.tools import list_ports
    com_list_all = list(list_ports.comports())
    power_set(vol=12, curr=5)