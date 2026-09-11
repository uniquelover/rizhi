import os.path
import time
import subprocess
import cv2
from frozen_dir import app_path
from utils.yaml_util import YamlRead
import shutil
from utils.log_util import glog
import numpy as np
import traceback
from utils.log_util import wprint, format_time
from utils.pic_util import match_ui, match_ui_mul, match_ui_zone, get_pos_touch
from video.video_util import CameraRecorder
import threading
from log_tool.gdata import Gdata
from scrcpy.util import scrcpy_swipe, scrcpy_touch, client_init
from utils.pic_util import m_imread, m_imwrite, check_period, cal_ssim
from press_android.util import audio_start, audio_stop, get_all_file_paths, mspeak, get_label_info, get_label_path, \
    get_pic_info
from video.model_check import execute_check_car_model
from video.demo import Testvalues
from airtest.core.android.adb import ADB
from airtest.core.android.n50_adb import N50_ADB
from press_android.util import get_label_info, get_all_file_paths, mspeak
# from log_tool.log_layout import ServerSignals
from PyQt5.QtCore import QTimer
from utils.dacarator import add_try_catch, sender_stable, run_in_thread, check_hardenv, check_adb_before_run
from byd import can_signal_test

pic_vad = None
template_vad = None
gap_vad = None
touch_sleep = None
g_cmd = None
audio_inst = None
label_dict = {}
# swipe_pos = {}  # Per-page swipe coordinates when a view requires scrolling.
label_pic = None
last_frame = None
switch = 'scrcpy'  # adb scrcpy
check_time = 2.5
gap_time = 1
keyboard_apk_path = f"{app_path}/config/ADBKeyboard.apk"

yml_file = f"{app_path}/data/conf.yml"
yamlobj = YamlRead(yml_file)
config_data_project = yamlobj.read_data()
project_default = config_data_project['share']['project']
content_project = config_data_project[project_default]['log']
android_ip = os.getenv("RIZHI_ADB_IP", "").strip() or content_project['android_ip']
adb_wifi_connect = content_project['adb_connect_wifi']

g_can_wait_func = None
g_can_wait_meta = None
g_selinux_relaxed = False


adb = None
if adb_wifi_connect:
    print("无线adb连接", android_ip)
else:
    print("有线adb")

# adb = N50_ADB(android_ip)


def get_runtime_adb():
    global adb
    target_serial = os.getenv("RIZHI_ADB_SERIAL", "").strip()
    target_ip = os.getenv("RIZHI_ADB_IP", "").strip()
    force_usb = os.getenv("RIZHI_CLI_FORCE_USB_ADB", "").strip() == "1"
    if target_serial:
        if not isinstance(adb, N50_ADB) or getattr(adb, "serialno", "") != target_serial:
            adb = N50_ADB(target_serial)
    elif target_ip:
        serial = f"{target_ip}:5555"
        if not isinstance(adb, N50_ADB) or getattr(adb, "serialno", "") != serial:
            adb = N50_ADB(serial)
    else:
        if force_usb:
            adb_path = os.getenv("RIZHI_CLI_ADB_PATH", "").strip() or r"D:\platform-tools\adb.exe"
            try:
                result = subprocess.run([adb_path, "devices"], capture_output=True, text=True)
                for line in result.stdout.splitlines()[1:]:
                    cols = line.split()
                    if len(cols) >= 2 and cols[1] == "device" and ":" not in cols[0]:
                        if not isinstance(adb, ADB) or getattr(adb, "serialno", "") != cols[0]:
                            adb = ADB(serialno=cols[0])
                        break
            except Exception:
                pass
        elif adb is None or isinstance(adb, N50_ADB):
            adb = ADB()
    return sync_adb_target(adb)


def ensure_adb_ready():
    global g_selinux_relaxed
    if adb_wifi_connect or g_selinux_relaxed:
        return
    try:
        get_runtime_adb().cmd_shell("setenforce 0")
    except Exception as exc:
        wprint(f"WARN: setenforce 0 failed: {exc}")
    finally:
        g_selinux_relaxed = True


def sync_adb_target(madb):
    target_serial = os.getenv("RIZHI_ADB_SERIAL", "").strip()
    target_ip = os.getenv("RIZHI_ADB_IP", "").strip()
    if target_serial:
        if hasattr(madb, "serialno"):
            madb.serialno = target_serial
        if hasattr(madb, "ip"):
            madb.ip = target_serial.rsplit(":", 1)[0]
    elif target_ip:
        serial = f"{target_ip}:5555"
        if hasattr(madb, "serialno"):
            madb.serialno = serial
        if hasattr(madb, "ip"):
            madb.ip = target_ip
    return madb


def mtouch(minst, pos, display_id=0, duration=None):
    if switch == 'adb':
        minst.madb.touch(pos, display_id=display_id)
    else:
        scrcpy_touch(minst.mscrcpy, display_id, pos, duration)


def mswipe(minst, pos1, pos2, display_id):
    if switch == 'adb':
        minst.madb.swipe(pos1, pos2)
    else:
        scrcpy_swipe(minst.mscrcpy, pos1, pos2, display=display_id)


def screen_android(minst, screen_id, spath='.', pic_name=None, ):
    """
    截图，支持 adb 和 scrcpy
    Args:
        minst: 实例
        screen_id: 屏幕 id
        spath: 保存路径
        pic_name: 保存的图片名称；如果不提供，则使用时间戳
    Returns:
    """
    global last_frame
    if switch == 'adb':
        tmp = f'-d {screen_id}' if screen_id else ''
        scmd = f'shell rm -f /sdcard/tmp.png; screencap  {tmp} -p /sdcard/tmp.png'
        minst.madb.cmd(scmd, ensure_unicode=False)
        screen_time = format_time()
        dfile = f'{spath}/{screen_time}.png'
        minst.madb.pull('/sdcard/tmp.png', dfile)
        screen = m_imread(dfile)
        return screen
    else:
        frame = minst.tmp_queve.get()
        fre = '' if pic_name is None else pic_name.split('_', 1)[1]
        pic_name = fre + '_' + format_time()
        if pic_name == "t1":
            pic_name = format_time()
        if pic_name == "t2":
            pic_name = format_time()
        dfile = f'{spath}/{pic_name}.png'
        wprint(f'# 截图: {dfile} ')
        m_imwrite(dfile, frame)
        return frame


def mtext(madb, content):
    """
    Send text input through ADBKeyboard.

    `content` is broadcast to the current focused input field.
    """
    # madb.cmd_shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {content}")
    sync_adb_target(madb)
    madb.cmd_shell(f"input text {content}")


def parse_numeric_arg(raw_value):
    text = str(raw_value).strip()
    try:
        return int(text)
    except ValueError:
        return float(text)

# @check_adb_before_run
def get_version(car_model, yml_file=f"{app_path}/data/conf.yml"):
    from utils.yaml_util import YamlRead
    from airtest.core.android.adb import ADB
    from airtest.core.android.n50_adb import N50_ADB
    yamlobj = YamlRead(yml_file)
    config_data_project = yamlobj.read_data()
    pos1 = tuple(config_data_project[car_model]['version']['pos'])
    text_zone = config_data_project[car_model]['version']['zone']
    adb_serial = os.getenv("RIZHI_ADB_SERIAL", "").strip()
    adb_ip = os.getenv("RIZHI_ADB_IP", "").strip()
    if adb_serial:
        adb1 = N50_ADB(adb_ip or adb_serial)
    elif adb_ip:
        adb1 = N50_ADB(adb_ip)
    else:
        adb1 = ADB()
    cmd = 'am start -S -n com.autolink.engineermode/com.autolink.engineermode.MainActivity'
    adb1.cmd_shell(cmd)
    time.sleep(2)
    adb1.touch(pos1)
    scmd = f'rm -f /sdcard/tmp.png; screencap -p /sdcard/tmp.png'
    adb1.shell(scmd)
    dfile = 'D:/11/engineermode.png'
    adb1.pull('/sdcard/tmp.png', dfile)
    screen1 = m_imread(dfile)
    android_ver = ""
    qnx_ver = ""
    # minst.madb.touch(pos, display_id=0)
    # mtouch(ui_inst, (x, y), display_id=0)
    from ocr_server.client import get_ocr
    # x1, y1, x2, y2 = [1227, 186, 1766, 301]
    x1, y1, x2, y2 = text_zone
    screen = screen1[y1:y2, x1:x2].copy()
    content = get_ocr(screen)
    cv2.imwrite('D:/11/version.png', screen)
    ver = []
    for a, _, _ in content:
        ver.append(a)
    print(ver, "ver value")
    try:
        if ver:
            if len(ver) == 3:
                android_ver = ver[0] + ver[2].split('_')[-1]
                qnx_ver = ver[1]
            if len(ver) == 2:
                android_ver = ver[0]
                qnx_ver = ver[1]
            return android_ver, qnx_ver
        else:
            return [], []
    except Exception as e:
        print(f"解析版本号出错: {e}")
        return [], []
    finally:
        time.sleep(1)
        adb1.cmd_shell("input keyevent KEYCODE_HOME")


go_exeception = False
# @check_adb_before_run
def press_test(ui_inst, sfile, conf={}, spath='.'):
    """
    Keep per-step image context so follow-up checks can use the correct screenshot state.
    `spath` is the screenshot output directory and `vad` is the score threshold.
    """
    dirpath_cur = None  # track the previous image directory between steps
    madb = ui_inst.adb
    with open(sfile, 'r', encoding='utf8') as fr:
        for line_cnt, line in enumerate(fr.readlines()):
            line = line.strip().lstrip('ufeff')
            print('\n')
            action, value = line.split(':')
            if action == "launch_times":
                run_times = int(value)
    for i in range(1, run_times+1):
        print("执行第{}次".format(i))
        if i == run_times:
            print("执行最后一次")
            go_exeception = True
        def excute_cmd(line, root, line_num):
            nonlocal dirpath_cur, index_touch
            nonlocal bool_res  # Store condition results for later if/else handling.
            # nonlocal info_list
            dongtai = False
            pic_info_dict = {}  # Cached metadata for the current reference images.
            action_sleep = touch_sleep  # Default post-action sleep duration.
            action, value = line.split(':')
            if '%' in value:  # % 璺熷姩浣滅殑鍝嶅簲鏃堕棿
                s1, s2 = value.split('%', 1)
                action_sleep = float(s2)
                info_list = s1.split()
            else:
                info_list = value.split()
            # Actions that work with images.
            # touch / ctouch: image match and tap, supports multiple screenshots.
            # check / check_not / check_text / exist: assertion-style checks.
            # screen / com_pic_same / com_pic_diff: screenshot and comparison helpers.
            # screen com_pic_same com_pic_diff
            # Audio actions.
            # speak audio_start audio_stop
            ##鏂囧瓧
            # text: type text after the cursor is already focused elsewhere.
            # Helper actions.
            # can swipe ptouch
            ##鍚庢湡鏀惧純浣跨敤
            # ctouch wait show
            # Extended actions.
            # wait_ui: wait for UI to appear with a custom timeout and threshold.
            info_list1 = []
            if len(info_list) > 1:
                info_list1 = info_list[1:]
            if action in ['touch', 'ctouch', 'check', 'check_not', 'exist']:  # `ctouch` is kept mainly for compatibility.
                # Load metadata for the target images, including swipe, crop and tap positions.
                # Newer configs prefer coordinates and metadata instead of binding a small image to a big image.
                # After finding the larger region, compare a finer sub-region using thresholds when needed.
                # This also avoids false matches caused by mismatched crop ranges.
                swipe_cord = None
                if len(info_list) > 1 and not info_list[0].endswith("_pass"):
                    info_list = info_list[:1]
                    dongtai = True
                    # info_list1 = info_list[1:]
                for item in info_list:
                    label_name = item.split('#')[0]
                    label_path = get_label_path(label_name, root, label_dict)
                    pic_info = get_pic_info(label_path)  # Metadata is enough when available; small-image fallback is legacy.
                    if pic_info and 'swipe' in pic_info and pic_info['swipe'] is not None:
                        swipe_cord = pic_info['swipe']
                    pic_info_dict[item] = (pic_info, label_path)
                if swipe_cord:
                    x0, y0, x1, y1 = swipe_cord  # Reuse one swipe path across multiple image states on the same page.
                    mswipe(ui_inst, (x0, y0), (x1, y1), display_id)
            if action == 'touch':
                if dongtai:
                    t_pos, index_touch = get_pos_touch(info_list, pic_info_dict, ui_inst, '', spath, pic_name=line_num)
                    wprint(f'#%% touch {t_pos}  index_touch:{index_touch}')
                    mtouch(ui_inst, t_pos, display_id=display_id, duration=int(info_list1[1]))
                else:
                    t_pos, index_touch = get_pos_touch(info_list, pic_info_dict, ui_inst, '', spath, pic_name=line_num)
                    wprint(f'#%% touch {t_pos}  index_touch:{index_touch}')
                    mtouch(ui_inst, t_pos, display_id=display_id)
            elif action == 'ctouch':
                pos, index_touch = get_pos_touch(info_list, pic_info_dict, ui_inst, '', spath, pic_name=line_num)
                # print("debug", info_list, pic_info_dict, pos, index_touch)
                if pos:
                    if info_list[index_touch].find('_pass') == -1:
                        wprint(f'# ctouch {pos} index: {index_touch}')
                    wprint(f'# 满足当前状态，不需要 touch')
                else:
                    wprint('# 满足当前状态，不需要 touch')
            elif action == 'check':
                if dongtai:
                    dfile = "D:/11/"
                    match_res = False
                    all_target = info_list1[4:]
                    x1, y1, x2, y2 = [int(item) for item in info_list1[:4]]
                    dynamic_pic = dfile+f"动态_{info_list[0]}.png"
                    screen = screen[y1:y2, x1:x2].copy()
                    dynamic_pic = dfile+f"动态_{info_list[0]}.png"
                    m_imwrite(dynamic_pic, screen)

                    for item in all_target:
                        label_name = item.split('#')[0]
                        label_path1 = get_label_path(label_name, root, label_dict)
                        print(label_path1, dynamic_pic)
                        if cal_ssim(label_path1, dynamic_pic):
                            match_res = True
                        print("动态检测目标通过")
                    if match_res:
                        print("动态检测目标通过")
                    else:
                        raise Exception('动态检测目标失败')
                else:
                    check_period(ui_inst, info_list, pic_info_dict, spath=spath, index=index_touch, score_vad=pic_vad,
                                 pic_name=line_num)
            elif action == 'check_not':
                try:
                    check_period(ui_inst, info_list, pic_info_dict, index=index_touch, score_vad=pic_vad, pic_name=line_num)
                    # wprint(aa)
                    raise Exception('图片匹配成功，不符合预期')
                except Exception as e:
                    wprint('图片没有匹配上，符合预期')
            elif action == 'exist':
                try:
                    check_period(ui_inst, info_list, pic_info_dict, index=index_touch, score_vad=pic_vad, pic_name=line_num)
                    bool_res = True
                except Exception as e:
                    bool_res = False
            elif action == 'check_text':
                # OCR text check within a fixed region
                from ocr_server.client import get_ocr
                target = info_list[0]
                state = False
                fre = line_num + "@" + target + "#"
                wdata = None
                if len(info_list[1:]) == 4:
                    x1, y1, x2, y2 = [int(item) for item in info_list[1:]]
                    screen = screen_android(ui_inst, '', spath=spath, pic_name=line_num)
                    screen = screen[y1:y2, x1:x2].copy()
                    content = get_ocr(screen)
                    if any(target in a for a, _, _ in content):
                        wprint(f"ocr 识别到 {target}")
                        state = True
                    wdata = screen
                else:
                    raise Exception("check_text 参数不足，需要文本+4个坐标")
                if not state:
                    if os.path.exists(Gdata.root_dir + '/diff/'):
                        wpath = Gdata.root_dir + '/diff/' + fre + format_time() + '.png'
                        m_imwrite(wpath, wdata)
                    raise Exception(f"ocr 没有识别到 {target}")
                else:
                    if os.path.exists(Gdata.root_dir + '/same/'):
                        wpath = Gdata.root_dir + '/same/' + fre + format_time() + '.png'
                        m_imwrite(wpath, wdata)
                        m_imwrite(wpath, wdata)
            elif action == 'text':
                # Type text into the current focused field.
                content = info_list[0]
                mtext(madb, content)
            elif action == 'com_pic_same':
                # Compare two local images and require them to match.
                pic1, pic2 = info_list
                data1 = m_imread(spath + '/' + pic1)
                data2 = m_imread(spath + '/' + pic2)
                pos = match_ui(data1, data2, score_vad=pic_vad)
                if not pos:
                    raise Exception('应该匹配上')
            elif action == 'com_pic_diff':
                # Compare two local images and require them to differ
                pic1, pic2 = info_list
                data1 = m_imread(spath + '/' + pic1 + '.png')
                data2 = m_imread(spath + '/' + pic2 + '.png')
                pos = match_ui(data1, data2, score_vad=pic_vad)
                if pos:
                    raise Exception('不应该匹配上')
            elif action == 'screen':
                pic_name = info_list[0]
                _, pic1 = screen_android(ui_inst, '', spath=spath, pic_name=pic_name)
                if len(info_list) == 5:
                    x1, y1, x2, y2 = [int(item) for item in info_list[1:]]
                    data = pic1[y1:y2, x1:x2]
                    if not pic_name.startswith(".png"):
                        pic_name = pic_name + ".png"
                    m_imwrite(spath + '/' + pic_name, data)
            elif action == 'ptouch':
                # Support either coordinate files or direct coordinate input.
                if len(info_list) == 1:
                    pic_txt = get_label_path(info_list[0], root, label_dict)
                    with open(pic_txt, 'r', encoding='utf8') as fr:
                        content = [item for item in fr.readlines() if item.strip()][0]
                        x, y = [int(item) for item in content.split()]
                elif len(info_list) == 2:
                    x, y = [int(item) for item in info_list]
                mtouch(ui_inst, (x, y), display_id=display_id)
            elif action == 'speak':
                # `speak` accepts plain text; wav input is played directly by the helper.
                content = info_list.pop()
                mspeak(content)
            elif action == 'audio_start':
                name, action_sleep = info_list
                audio_start(name, action_sleep)
            elif action == 'audio_stop':
                audio_stop()
            elif action == 'can':
                id_value, id_name, sig, value = info_list[:4]
                cycle = info_list[-1] if len(info_list) == 5 else 100
                ui_inst.inst_can.msg_send(id=id_value, idname=id_name, signame=sig, value=value, cycle_time=cycle, )
            elif action == 'wait':
                item = float(info_list[0])
                time.sleep(item)
            elif action == 'swipe':
                x0, y0, x1, y1 = [int(item) for item in info_list]
                mswipe(ui_inst, (x0, y0), (x1, y1), display_id)
            elif action == 'show':  # Print debug information during script development.
                minfo = ''.join(info_list)
                wprint(f'% minfo:{minfo}')

            elif action == 'check_car_model_color':
                color = info_list[0]
                wprint(f'% color:{color}')
                execute_check_car_model(color)
            elif action == 'launch_times':
                # wprint(f'% case executed: {info_list[0]} times')
                pass
            elif action == 'cmd':
                commands = " ".join(info_list)
                # print(commands, "command to execute")
                get_runtime_adb().cmd_shell(commands)
            # elif action == "can_test":
            #     print("can 外发信号校验测试", info_list)
            #     if len(info_list) == 4:
            #         msgs, sigs, tars, tfs = [item for item in info_list]
            #         can_signal_test(msgs, sigs, int(tars), int(tfs))
            elif action == "can_test":
                print("can外发信号校验测试", info_list)

                if len(info_list) >= 4:
                    msgs = info_list[0]
                    sigs = info_list[1]
                    tars = parse_numeric_arg(info_list[2])
                    tfs = int(info_list[3])

                    mode = 'start'
                    if len(info_list) > 4 and info_list[4].lower() == 'check':
                        mode = 'check'
                    can_signal_test(msgs, sigs, tars, tfs, action=mode)
                else:
                    raise Exception('can_test 参数不足，需要至少4个参数')
            else:
                raise Exception(f'action: {action} not supported')
            if action in ['touch', 'ctouch', 'ptouch', 'text', 'speak']:
                time.sleep(action_sleep)
        # Record the failing command and related screenshot name.
        global g_cmd, g_pic
        with open(sfile, 'r', encoding='utf8') as fr:
        # Used to record the failing command and related image name.
            is_if = False  # Whether the current block is under an `if`.
            is_else = False  # Whether the current block is under an `else`.
            bool_res = False  # Result flag for `exists`/conditional branches.
            index_touch = 0  # Matching index shared across steps for multi-image states.
            # Whether the current line is indented under an if/else block.
            sr_index = os.path.basename(sfile).split('_', 1)[0]
            display_id = conf.get('display', 0)
            label_path = label_pic  # Current label root, prevents repeated renaming issues.
            for line_cnt, line in enumerate(fr.readlines()):
                line = line.strip().lstrip('ufeff')
                print('\n')
                wprint(f'@@行号:{line_cnt + 1} line: {line}')
                line_num = sr_index + '_' + str(line_cnt + 1)
                if not line.strip() or Gdata.quit_press:
                    break
                if 'label_path' in line:  # label_path is None and
                    label_path = line.split('label_path')[1].replace(':', '').strip()
                    continue
                ui_inst.mid_signal.emit({'plain_text': line})
                # Explicitly switch the active display before the next actions.
                if line.find('display:') > -1:
                    dispaly = line.replace('display:', '').strip()
                    display_id = conf['touch'][dispaly]
                    init_scrcpy(ui_inst, display=display_id)
                    continue
                # Reset per-run state each time `pic_vad` is declared.
                if line.find('pic_vad:') > -1:
                    global pic_vad
                    tmp = str(line.replace('pic_vad:', '').strip())
                    if tmp == 'default':
                        pic_vad = conf["pic_vad"]
                    else:
                        pic_vad = float(line.replace('pic_vad:', '').strip())
                    continue
                is_indent = False
                line = line.replace('\n', '')
                g_cmd = line  # Store the current command for failure reporting.
                # Distinguish `if` / `else` blocks from normal statements.
                # Only a single indentation level is supported here.
                if line.startswith('if'):
                    is_if = True
                    is_else = False
                    line = line[2:]
                elif line.startswith('else'):
                    is_else = True
                    is_if = False
                    continue
                    # line = line[4:]
                else:
                    # Four spaces indicate the nested block body.
                    if line.startswith('    '):
                        is_indent = True
                    else:
                        # Leaving indentation exits the current conditional block.
                        is_if = False  # Whether the current block is under an `if`.
                        is_else = False
                        bool_res = False  # Reset the previous condition result.
                if is_indent:
                    # Inside indentation, decide whether this branch should run.
                    if is_if and not bool_res:
                        wprint(f'# is_indent:{is_indent}  is_if:{is_if} bool_res:{bool_res} ')
                        continue
                    elif is_else and bool_res:
                        continue
                # Decide whether an `else` branch should execute.
                elif is_else and bool_res:  # Skip `else` when the `if` branch has already succeeded.
                    continue
                if line.strip() and line.strip()[0] == '#':  # Ignore comment lines.
                    continue
                excute_cmd(line, label_path, line_num)
def func_press_android(ui_inst):
    func_press_android_mode(ui_inst, mode='loop')
def init_can(ui_inst):
    from zlgsendcan.can_inst import CanSender
    yfile = f'{app_path}/config/log_tool.yml'
    # nts
    inst_can = CanSender(yfile)
    # inst_can = None
    ui_inst.inst_can = inst_can
def tear_down():
    from zlgsendcan.parseDBC import DbcInit, GlobleValue
    global g_can_wait_func, g_can_wait_meta
    DbcInit.data = {}
    GlobleValue.flag = False
    g_can_wait_func = None
    g_can_wait_meta = None
    time.sleep(1)  # Leave a short grace period for background threads to exit.
    ##鏀堕泦鏃ュ織

def get_ui_inst(ui_inst):
    ui_inst.mid_signal.emit({'plain_text': "请先添加(中控)测试用例!!!"})
def func_press_android_mode(ui_inst, mode=None):
    # mode: loop runs continuous pressure tests; None runs a single smoke pass.
    func_press_android_mode_func(ui_inst, mode=mode)
def func_record(recorder, dst):
    recorder.start_recording(output_path=dst)
def init_scrcpy(ui_inst, display=0):
    if ui_inst.mscrcpy is not None:
        ui_inst.mscrcpy.destroy()

    import queue
    mscrcpy = client_init(display,ui_inst)  # Recreate the scrcpy client for the selected display.
    tmp_queve = queue.Queue(maxsize=1)
    mscrcpy.register(tmp_queve)
    ui_inst.mscrcpy = mscrcpy
    ui_inst.tmp_queve = tmp_queve  # Queue used to receive scrcpy frames.

# case_numbers = 0
def func_press_android_mode_func(ui_inst, mode=None):
    global touch_sleep, pic_vad, gap_vad, label_pic
    global label_dict
    # global case_numbers
    ui_inst.mscrcpy = None
    ui_inst.check_env()
    init_can(ui_inst)
    init_scrcpy(ui_inst)
    # if_input_method = adb.get_input_method()
    # if if_input_method:
    #     print("ADBKeyboard is already installed; no need to reinstall")
    # else:
    # print("ADBKeyboard is not installed; installing now, please wait")
    # try:
    #     adb.install_app(f"{keyboard_apk_path}")
    #     time.sleep(10)
    #     adb.cmd_shell("ime enable com.android.adbkeyboard/.AdbIME")
    #     time.sleep(1)
    #     adb.cmd_shell("ime set com.android.adbkeyboard/.AdbIME")
    # except Exception as e:
    #     print(f"安装出错,{e}")
    #     traceback.print_exc()
    yml_file = f'{app_path}/press_android/conf.yml'
    yamlobj = YamlRead(yml_file).read_data()
    car = yamlobj['share']['project']  # Current vehicle project key.
    conf_data = yamlobj[car]  # Project-specific pressure-test configuration.
    script_fold = f'{app_path}/press_android/{conf_data["script_fold"]}'
    script_list = get_all_file_paths(script_fold)
    if len(script_list) == 0:
        ui_inst.mid_signal.emit({'plain_text': "请先添加(中控)测试用例!!!"})
        raise Exception("测试脚本为空，请先添加(中控)测试用例!!!")
    Testvalues.android_cases = len(script_list)
    label_pic = f'{app_path}/press_android/{conf_data["label_pic"]}'
    spath = conf_data["spath"]
    touch_sleep = conf_data["touch_sleep"]
    camera_state = conf_data["camera"]
    pic_vad = conf_data["pic_vad"]
    gap_vad = conf_data["gap_vad"]
    label_dict = get_label_info(label_pic)  # Load label positions and metadata.
    if os.path.exists(spath):
        shutil.rmtree(spath)
    os.makedirs(spath)
    loop = pow(2, 31) - 1 if mode == 'loop' else 1
    cur_time = format_time()
    nfold = f'{app_path}/{cur_time}'  # Root folder for this run's per-case artifacts.
    os.makedirs(nfold)
    result = {}  # Per-script execution results.
    ui_inst.camera = None
    # case_numbers = 0
    for i in range(loop):
        wprint(f'\n\n## loop :{i}')
        res = f'第{i}轮测试'
        ui_inst.mid_signal.emit({'plain_text': res})
        case_numbers = 0
        for script_file in script_list:  # Iterate over script files read from disk.
            Testvalues.test_types = "中控"
            # case_numbers = 0
            # print(case_numbers, "case_numberssssssss!@@@@")
            case_numbers = case_numbers + 1
            tmp = os.path.splitext(os.path.basename(script_file))[0]
            if i == 0:
                sfold = f'{nfold}/{tmp}'
                if not os.path.exists(sfold):
                    os.makedirs(sfold)
            wprint(f'\n\n文件是 {os.path.basename(script_file)}')
            script_name = os.path.basename(script_file)
            try:
                res = f'\n##{script_name}开始运行'
                ui_inst.mid_signal.emit({'plain_text': res})
                # Record the test run when camera capture is enabled.
                if camera_state == 'open':
                    ui_inst.camera = CameraRecorder()
                    producer_thread = threading.Thread(target=func_record, args=(ui_inst.camera, sfold))  # frame_queue
                    producer_thread.start()
                press_test(ui_inst, script_file, conf=conf_data, spath=sfold)  # conf_data
                res = f'%%{script_name} 执行通过'
                ui_inst.mid_signal.emit({'plain_text': res})
                result[script_name] = True
            except Exception as e:
                # if go_exeception:
                res = f'%%{script_name} 执行失败'
                ui_inst.mid_signal.emit({'plain_text': res})
                result[script_name] = False

                for k1, v1 in result.items():
                    if v1 is False:
                        if len(find_files_starting_with_id("D:\\11\\diff", str(int(k1.split('_')[0])))) >= 1:
                            Testvalues.diff_datas[int(k1.split('_')[0])] = find_files_starting_with_id("D:\\11\\diff", str(int(k1.split('_')[0])))[-1]
                    glog.error(
                        f'执行失败 轮次:{i} 用例:{os.path.basename(script_file)}, 指令:{g_cmd}, 信息:{traceback.format_exc()}')
            finally:
                # if go_exeception:
                Testvalues.total_cases -= 1
                Testvalues.android_cases -= 1
                print(
                    f"--------已执行完{case_numbers}条中控用例,还剩{Testvalues.android_cases}条中控用例,全部还剩{Testvalues.total_cases}条用例待执行!")
                ui_inst.mid_signal.emit({'plain_text': '#init_clr'})
                ui_inst.progress_updated.emit(case_numbers, Testvalues.android_cases, Testvalues.total_cases)
                if ui_inst.camera:
                    ui_inst.camera.stop_recording()  # Stop camera recording.
                if loop != 1:
                    Gdata.quit_press = True  # stop long-running pressure mode
                # result[script_name] = False  # Legacy note for Excel export flow.
                for k, v in result.items():
                    Testvalues.test_datas[int(k.split('_')[0])] = v
                tear_down()  # 周立功



    # Report export example.
    #nts
    # Report export example kept here for reference only.
    # from press_android.write_report import update_excel_with_file
    # excel_path = app_path + '/press_android/' + conf_data['write']['excel_path']
    # sheet = conf_data['write']['sheet']
    # title_index = conf_data['write']['title_index']
    # title_write = conf_data['write']['title_write']
    # skiprows = conf_data['write']['skiprows']
    # update_excel_with_file(excel_path, sheet, title_write, title_index, result, skiprows)

def find_files_starting_with_id(path, s):
    """查找指定路径下所有以失败 id 开头的文件名。"""
    files = []
    for item in os.listdir(path):
        if os.path.isfile(os.path.join(path, item)) and item.startswith(s):
            files.append(os.path.join(path, item))
    return files


if __name__ == '__main__':
    pass




