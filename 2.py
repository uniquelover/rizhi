import os
import sys

# sys.path.append('..')
from zlgsendcan.can_inst import CanSender
from frozen_dir import app_path
import time
from byd import *
from zlgsendcan.parseDBC import DbcInit, GlobleValue
from datetime import datetime
from video.demo import global_time
from yolo11_release.demo import *
from yolo11_release.bydapi import *
from airtest.core.qnx.n50_qnx import N50_QNX
from airtest.core.android.adb import ADB
from video.demo import Testvalues

# 通过exec传入的外部变量
# uinst=p_inst
# logger=p_logger
# display_id = 4
# logger.info('begin now')
yfile = f"{app_path}/data/conf.yml"
adb = ADB()
uinst_block = N50_QNX(adb_obj=adb, yml_file=yfile, type='block')
uinst = N50_QNX(adb_obj=adb, yml_file=yfile)
try:
    uinst_block.start_video(1)
    # 操作步骤
    time_spend = []
    t1_start_time = time.time()
    msg_send(id=0x23B, idname='FLZCU_1', signame='LHTurnlightSts', cycle_time=20, value=0x1, )
    gap_sleep(5)
    t_spend_time = round(time.time() - t1_start_time, 2)
    time_spend.append(t_spend_time)

except Exception as e:
    logger.error(str(e))
else:
    test_res = []
    GlobleValue.thread_run = False
    target_folder = os.getcwd() + r"\\out"
    p = os.getcwd()
    case_id = 2
    res_dict = {}
    exp_img = os.path.join(p, 'pic', f'{case_id}.png')
    target_path = target_folder + f"\\{case_id}"
    # with open(os.path.join(target_path, 'res.yml'), 'w', encoding='utf-8') as file:
    #     yaml.dump(data, file, allow_unicode=True)
    uinst.stop_video(1, video='res.avi', save_path=target_path)
    video_name = get_video_name(target_path)
    chcker1 = VideoChecker('yolo', video_path=target_path + f"\\{video_name}", class_name_target=["行车灯-3.png"], project='t1v')
    yolo_data1 = chcker1.check_video()
    result1 = check_target(yolo_data1, target='左转指示灯', action='点亮')
    res_dict['步骤1'] = result1
    test_res.append(result1)
    Testvalues.test_datas[case_id] = res_dict
finally:
    GlobleValue.thread_run = False
    DbcInit.data = {}
    GlobleValue.thread_obj = {}