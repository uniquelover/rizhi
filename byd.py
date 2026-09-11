import time
import sys
import os
#sys.path.append("..")
from frozen_dir import app_path
from zlgsendcan.can_inst import CanSender
from zlgsendcan.zlgserver import verify_signal_change
# from byd import *
from power import power_set
from frozen_dir import app_path
from check_excel import parse_dbc_and_get_signals
# 打开 CAN
yfile = os.path.join(app_path, 'config', 'log_tool.yml')
dbc_file = os.path.join(app_path, 'zlgsendcan', 'EEA5.1 Message List IC CANFD_V1.4.1_20260108_ICC.dbc')
can_inst = None


def get_can_inst():
    global can_inst
    if can_inst is None:
        can_inst = CanSender(yfile)
    return can_inst


# Add a small gap between steps so the UI state has time to settle.
def gap_sleep(dur=None):
    if dur is None:
        dur = 2
    time.sleep(dur)


def restart():
    inst = get_can_inst()
    inst.msg_send(id='0x50A', value='00 11 22 33 44 55 66 77')
    gap_sleep(3)
    inst.msg_send(id=0x12D, idname='Left_BCM_0x12D', signame='BCMPower_Gear_12D', cycle_time=50, value=0x3, )
    

def sleep_can():
    inst = get_can_inst()
    inst.msg_send(id=0x12D,idname='Left_BCM_0x12D', signame='BCMPower_Gear_12D', value=0x1,)
    # 0x50A 报文停止发送
    inst.msg_stop_normal()


def on_gear():
    # qt
    get_can_inst().msg_send(id=0x12D, idname='Left_BCM_0x12D', signame='BCMPower_Gear_12D', cycle_time=50, value=0x1, )


def msg_send(id=None, mutil_sig=None, idname=None, signame=None, value=None,cycle_time=None, is_crc='0', cnt=None,pro_name=None):
    inst = get_can_inst()
    if cnt is None:
        # print("一直发")
        inst.msg_send(id=id, idname=idname, signame=signame, value=value, cycle_time=cycle_time, is_crc=is_crc,pro_name=pro_name)
    else:
        print("单帧发信号")
        inst.msg_send(id=id, idname=idname, signame=signame, value=value, cycle_time=cycle_time, send_num=cnt, is_crc=is_crc,pro_name=pro_name)

# def msg_send(id=None, idname=None, signame=None, value=None,cycle_time=None, cnt=None):
#     if cnt is None:
#         print("一直发")
#         can_inst.msg_send(id=id, idname=idname, signame=signame, value=value, cycle_time=cycle_time,)
#     else:
#         print("单帧发")
#         can_inst.msg_send(id=id, idname=idname, signame=signame, value=value, cycle_time=cycle_time, send_num=cnt)


# msg_stop(id=0x2A6, dur=0.5)
def msg_stop(id=None,dur=0.5):
    """
    id 信号的 id
    idname 信号名称
    """
    print("执行 msg_stop 方法...")
    result = parse_dbc_and_get_signals(dbc_file, id)
    get_can_inst().msg_stop(idname=result['message_name'], dur=dur)

    # for idx, signal in enumerate(result["signals"], 1):
    #     print(signal['name'])
    #     can_inst.msg_stop(idname=signal['name'],dur=dur)


def reg_vol(vol=None, curr=None, state='on'):
    power_set(vol)


def can_signal_test(msg_name, signal_name, target_val, total_frames, action='start'):
    """
    分步式 CAN 信号校验
    action:
        'start' : 启动后台监听（点击前执行）
        'check' : 阻塞等待结果（点击后执行）
    """
    import press_android.press_android as main_module

    def _start_wait_task():
        inst = get_can_inst()
        # Start from a clean receive buffer so a previous case does not leak frames into this check.
        try:
            inst.clear_buffer()
            print("[CAN监听] 已清理接收缓存")
        except Exception as e:
            print(f"[CAN监听] 清理接收缓存失败，继续执行: {e}")
        main_module.g_can_wait_func = inst.signals_val_check(msg_name, signal_name, target_val, total_frames)
        main_module.g_can_wait_meta = (msg_name, signal_name, target_val, total_frames)

    if action == 'start':
        print(f"[CAN监听] 正在启动监听: {msg_name}.{signal_name} = {target_val}")
        _start_wait_task()
        return True

    elif action == 'check':
        print("[CAN验证] 正在检查结果...")

        current_meta = getattr(main_module, 'g_can_wait_meta', None)
        target_meta = (msg_name, signal_name, target_val, total_frames)
        if main_module.g_can_wait_func is None or current_meta != target_meta:
            print(f"[CAN验证] 当前无匹配监听，自动重建: {msg_name}.{signal_name} = {target_val}")
            _start_wait_task()

        try:
            main_module.g_can_wait_func()
            print("[CAN验证] 测试通过")
            main_module.g_can_wait_func = None
            main_module.g_can_wait_meta = None
            return True
        except Exception as e:
            print(f"[CAN验证] 失败: {e}")
            main_module.g_can_wait_func = None
            main_module.g_can_wait_meta = None
            raise Exception(f"信号校验失败: {e}")

def sleep(n):
    time.sleep(n)


def get_video_name(path):

    print(f"路径: {path}")
    for f in os.listdir(path):
        if f.endswith(".avi"):
            print(f)
            return f
    else:
        print("当前路径下没有视频文件")
        return None


if __name__ == "__main__":

    # msg_send(id=0x314, idname='ADS_COM_2', signame='FCM_2_IHCfunctionSts', cycle_time=50, value=0x2, )
    # time.sleep(5)
    can_signal_test('ICC_ZCU_25', 'ICC_AutoFoldSts', 1)




