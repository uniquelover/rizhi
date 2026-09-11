# 校验生成脚本基础数据是否匹配
import traceback

from cantools.database import Database
import cantools
import os.path
import shutil
import openpyxl
import re
import time
# from dbcAnalyze import DbcAnalyze
from openpyxl.styles import PatternFill, Alignment, Font, Border, Side
from openpyxl.utils import get_column_letter
from frozen_dir import app_path
from utils.yaml_util import YamlRead


yml_file = f"{app_path}/data/conf.yml"
yamlobj = YamlRead(yml_file)
config_data_project = yamlobj.read_data()
project_default = config_data_project['share']['project']

red_fill = PatternFill(
    fill_type="solid",  # 纯色填充
    start_color="FF0000",  # 红色（RGB: #FF0000）
    end_color="FF0000"  # 纯色填充时 start 和 end 颜色相同
)

green_fill = PatternFill(
    fill_type="solid",  # 纯色填充
    start_color="00FF00",  # 绿色（RGB: #00FF00）
    end_color="00FF00"  # 纯色填充时首尾颜色相同
)


def _normalize_case_text(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _load_android_case_name_map():
    scripts_dir = os.path.join(app_path, "press_android", "scripts")
    case_name_map = {}
    if not os.path.isdir(scripts_dir):
        return case_name_map

    for name in os.listdir(scripts_dir):
        if not name.endswith(".txt"):
            continue
        stem = os.path.splitext(name)[0]
        if "_" not in stem:
            continue
        case_id, case_name = stem.split("_", 1)
        try:
            case_name_map[int(case_id)] = case_name
        except ValueError:
            continue
    return case_name_map


def _match_case_id_from_row(row, normalized_case_name_map, matched_cases, allowed_case_ids=None):
    row_texts = []
    for cell in row[:8]:
        normalized = _normalize_case_text(cell.value)
        if normalized:
            row_texts.append(normalized)

    for case_id, script_case_name in normalized_case_name_map.items():
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id in matched_cases or not script_case_name:
            continue
        for row_text in row_texts:
            if script_case_name in row_text or row_text in script_case_name:
                return case_id
    return None


def _match_t1v_smoke_case_id(row, matched_cases, allowed_case_ids):
    feature = _normalize_case_text(row[3].value if len(row) > 3 else None)
    step = _normalize_case_text(row[5].value if len(row) > 5 else None)

    t1v_rules = {
        5: [("桌面界面", "桌面保持显示")],
        6: [("桌面3d壁纸", "左右滑动壁纸")],
    }

    for case_id, patterns in t1v_rules.items():
        if case_id in matched_cases or case_id not in allowed_case_ids:
            continue
        for feature_hint, step_hint in patterns:
            if feature_hint in feature and step_hint in step:
                return case_id
    return None


def _find_header_row(sheet, required_headers):
    for row_idx in range(1, min(sheet.max_row, 10) + 1):
        values = [sheet.cell(row_idx, col_idx).value for col_idx in range(1, sheet.max_column + 1)]
        if all(header in values for header in required_headers):
            return row_idx, values
    raise ValueError(f"未找到表头行: {required_headers}")


def process_excel_to_python_files(excel_path, start, end):
    """
        excel_path:  包含脚本的excel文件
        outfold:  自动化脚本的输出路径
    """
    global signame, message
    workbook = openpyxl.load_workbook(excel_path)
    sheet = workbook.active  # 获取活动工作表
    # 获取第一行作为列标题
    headers = [cell.value for cell in sheet[1]]  # 获取第一行的列标题

    try:

        column_prerequisite_code = headers.index("前提代码") + 1  # 找到“前提代码”列的索引
        column_prerequisite = headers.index("前提条件") + 1
        column_steps = headers.index("步骤描述") + 1
        column_automation = headers.index("自动化") + 1  # 找到“自动化”列的索引
        column_id = headers.index("编号") + 1
        column_res = headers.index("预期结果") + 1
        column_large_title = headers.index("需求大标题") + 1
        # add new codes
        column_signame = headers.index("signame校准") + 1
        column_add_gap = headers.index("补充gap_sleep") + 1
        column_del_gap = headers.index("删除多余gap_sleep") + 1
        column_res_times = headers.index("结果次数校准") + 1

    except ValueError:
        print("列标题中未找到 '前提代码' 或 '自动化'，请检查 Excel 文件格式。")

    cnt = 1
    for row in sheet.iter_rows(min_row=2, values_only=False):  # 从第2行开始读取数据，不使用 values_only=True

        cnt += 1
        if cnt < start:
            continue
        if cnt == end:
            break

        cell = row[column_prerequisite_code - 1]  # 获取前提代码单元格
        prerequisite_code = cell.value  # 获取前提代码的值

        # 检查是否为合并单元格
        merged_cells = sheet.merged_cells.ranges  # 获取所有合并单元格的范围
        merged_range = None
        merged_ranges = []

        for mr in merged_cells:
            merged_ranges.append(str(mr))

        is_merged = False
        for merged_cell in merged_cells:
            if cell.coordinate in merged_cell:  # 如果当前单元格在合并单元格范围内
                is_merged = True
                merged_range = merged_cell
                break

        # cell = row[column_prerequisite_code - 1]  # 获取前提代码单元格
        # prerequisite_code = cell.value  # 获取前提代码的值

        pre_cell = row[column_prerequisite - 1]
        prerequisite = pre_cell.value

        # 预期结果
        test_result = []

        # res_cell = row[column_res - 1]
        # res = res_cell.value

        # 需求大标题
        requirement_large_title = row[column_large_title - 1]
        requirement_vaule = requirement_large_title.value

        # 测试步骤
        test_stepss = []
        if is_merged:
            step_start_row = merged_range.min_row
            step_end_row = merged_range.max_row
            target_light = ""
            for i in range(step_start_row, step_end_row + 1):
                st = 0
                step_merged = sheet.cell(row=i, column=column_steps).value
                auto_merged = sheet.cell(row=i, column=column_automation).value
                result_merged = sheet.cell(row=i, column=column_res).value
                for k1, v1 in enumerate(auto_merged.split('\n')):
                    if v1 == "gap_sleep(3)" or v1 == "sleep(180)":
                        st += 1

                for k2, v2 in enumerate(result_merged.split('\n')):
                    print(result_merged.split('\n'), "v2....")
                    # if "闪烁" or "点亮" in result_merged.split('\n')[0]:
                    #     print(result_merged.split('\n')[0].split("灯")[0].split(".")[-1],"dengdeng")
                    #     target_light = result_merged.split('\n')[0].split("灯")[0].split(".")[-1] + "灯"
                    if "指示灯熄灭" in v2:
                        target_light = requirement_vaule.split(".")[-1]
                        v2 = v2.replace("指示灯", target_light)
                        sheet.cell(row=i, column=column_res).value = v2
                if len(step_merged.split('\n')) > st:  # 步骤和代码不一致
                    test_stepss.append(step_merged)
                elif len(step_merged.split('\n')) == st:  # 步骤和代码一致
                    for t1, t2 in enumerate(step_merged.split('\n')):
                        test_stepss.append(t2)
                    # for r1, r2 in enumerate(step_merged.split('\n')):
                    #     test_stepss.append(r2)
                else:
                    pass
                    # print("非法数据，请重新校验")

                if len(result_merged.split('\n')) > st:  # 步骤和代码不一致
                    test_result.append(result_merged)
                    # test_result.append(result_merged)
                elif len(result_merged.split('\n')) == st:  # 步骤和代码一致
                    for r1, r2 in enumerate(result_merged.split('\n')):
                        test_result.append(r2)
                    # for r1, r2 in enumerate(step_merged.split('\n')):
                    #     test_stepss.append(r2)
                else:
                    pass
                    # print("非法数据，请重新校验")

                # if step_merged is not None:
                #     test_stepss.append(step_merged)
            # print(test_stepss,"合并单元格的步骤")
            steps = test_stepss

            # for i in range(step_start_row, step_end_row + 1):
            #     rt = 0
            #     result_merged = sheet.cell(row=i, column=column_res).value
            #     auto_merged = sheet.cell(row=i, column=column_automation).value

            #     if step_merged is not None:
            #         test_result.append(result_merged.split('\n'))
            # print(test_result, "合并的预期结果。。。")
            res = test_result
        else:
            test_steps = row[column_steps - 1]
            steps = test_steps.value

            res_cell = row[column_res - 1]
            res = res_cell.value

        id_cell = row[column_id - 1]
        case_id = id_cell.value

        auto_cell = row[column_automation - 1]
        auto = auto_cell.value

        res_cell = row[column_res - 1]
        res = res_cell.value

        if auto is not None:
            if auto.split('\n')[-1] == "gap_sleep(3)":
                print("Has gap_sleep(3)")
                row[column_add_gap - 1].value = "Yes"
                # continue
            else:
                print("No gap_sleep(3)")
                row[column_add_gap - 1].value = "No"
                new_data = auto + "\ngap_sleep(3)"
                row[column_automation - 1].value = new_data
        else:
            print("空单元格。。。")
            continue
        gap_counter = 0
        # res_counter = res.count('.')
        if auto is not None:
            for i in auto.split('\n'):
                print(i)
                if i == "gap_sleep(3)":
                    gap_counter += 1

        if res is not None:

            res_counter = res.count('.')
            if gap_counter == res_counter:
                row[column_res_times - 1].value = "Yes"
                row[column_res_times - 1].fill = green_fill
            else:
                row[column_res_times - 1].value = "No"
                row[column_res_times - 1].fill = red_fill
        else:
            print("结果为空。。。")

    workbook.save("f4_modified.xlsx")
    # for i in auto.split('\n'):
    # 	print(i)


# if i.startswith("msg_send"):
# 	for s in i.split(','):
# 		# print(s.strip())
# 		if s.strip().startswith("signame"):
# 			print(s.split('=')[1])


def parse_dbc_and_get_signals(dbc_path, message_id):
    """解析 DBC 文件并获取指定报文 ID 的所有信号信息
    
    Args:
        dbc_path (str): DBC 文件路径
        message_id (int): 要查询的报文ID (十进制或十六进制形式)
    
    Returns:
        list: 包含所有信号字典的列表，格式示例：
            [{
                "name": "EngineSpeed",
                "start_bit": 8,
                "length": 16,
                "scale": 0.125,
                "offset": 0,
                "unit": "rpm",
                "is_signed": False
            }, ...]
    """
    try:
        # 加载 DBC 文件
        db: Database = cantools.database.load_file(dbc_path)

        # 查找对应报文
        message = db.get_message_by_frame_id(message_id)

        signals_info = []
        for signal in message.signals:
            # 提取信号关键信息
            signal_data = {
                "name": signal.name,
                "start_bit": signal.start,
                "length": signal.length,
                "scale": signal.scale,
                "offset": signal.offset,
                "unit": signal.unit or "N/A",
                "is_signed": signal.is_signed,
                "min": signal.minimum,
                "max": signal.maximum,
                "receivers": signal.receivers,
                "comment": signal.comment or ""
            }
            signals_info.append(signal_data)

        return {
            "message_id": hex(message.frame_id),
            "message_name": message.name,
            "signals": signals_info
        }

    except KeyError:
        raise ValueError(f"报文ID 0x{message_id:X}未在DBC文件中找到")
    except Exception as e:
        raise RuntimeError(f"解析DBC文件失败:{str(e)}")


def _write_test_result(types, start, end, tests_result, excel_path, fail_diff):
    """
        types: 测试类型(冒烟测试/全功能测试)
        start: 原始用例查询目标id起点
        end: 原始用例查询目标id终点
        test_result：用例每个步骤测试的结果，Ture表示通过,False表示未通过
        excel_paths: 写入测试结果的Excel表
        fail_diff：写入失败用例和预期结果的对比图
    """
    from datetime import date
    td = date.today()
    test_date = td.strftime("%Y-%m-%d")

    from press_android.press_android import get_version

    android_version = ""
    if project_default == "N50":
        android_version, qnx_version = get_version("N50")
    elif project_default == "N51":
        android_version, qnx_version = get_version("N51")
    elif project_default == "N80":
        android_version, qnx_version = get_version("N80")
    elif project_default == "T1V":
        android_version, qnx_version = get_version("T1V")
    else:
        print("车型尚未录入配置，暂为空")

    global signame, message
    workbook = openpyxl.load_workbook(excel_path)
    sheet = workbook.active  # 获取活动工作表

    if types == "smoke":
        header_row, headers = _find_header_row(
            sheet,
            ["一级功能", "功能点", "自动化测试结果", "测试日期", "测试版本", "对比图"],
        )
        data_start_row = header_row + 1

        column_id = headers.index("一级功能") + 1
        column_auto_test_result = headers.index("自动化测试结果") + 1
        column_auto_test_date = headers.index("测试日期") + 1
        column_diff_pic = headers.index("对比图") + 1
        column_auto_test_version = headers.index("测试版本") + 1
        column_auto_test_notes = headers.index("备注") + 1

        # 清除上一次的测试结果
        for cell in sheet[get_column_letter(column_auto_test_result)][data_start_row - 1:]:
            cell.value = None
            cell.fill = PatternFill(fill_type="none")
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # 清除上一次的测试日期
        for cell in sheet[get_column_letter(column_auto_test_date)][data_start_row - 1:]:
            cell.value = None
            cell.fill = PatternFill(fill_type="none")
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # 清除上一次测试失败图的链接
        for cell in sheet[get_column_letter(column_diff_pic)][data_start_row - 1:]:
            cell.value = None
            cell.hyperlink = None
            cell.fill = PatternFill(fill_type="none")
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # 清除上次测试版本号
        for cell in sheet[get_column_letter(column_auto_test_version)][data_start_row - 1:]:
            cell.value = None
            cell.fill = PatternFill(fill_type="none")
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # 清除上次测试报告备注
        for cell in sheet[get_column_letter(column_auto_test_notes)][data_start_row - 1:]:
            cell.value = None
            cell.fill = PatternFill(fill_type="none")
            cell.alignment = Alignment(horizontal='center', vertical='center')

        result_map = {}
        for k, v in tests_result.items():
            if isinstance(v, dict):
                result_map[k] = all(v.values())
            else:
                result_map[k] = bool(v)

        matched_cases = set()
        is_t1v_smoke = project_default == "T1V"

        for row_index, row in enumerate(
            sheet.iter_rows(min_row=data_start_row, values_only=False),
            start=data_start_row,
        ):
            id_cell = row[column_id - 1]
            caseid = id_cell.value
            matched_case_id = None

            if caseid in result_map:
                matched_case_id = caseid
            else:
                try:
                    caseid_int = int(caseid)
                except (TypeError, ValueError):
                    caseid_int = None
                if caseid_int in result_map:
                    matched_case_id = caseid_int

            if matched_case_id is None and is_t1v_smoke and row_index in result_map:
                matched_case_id = row_index

            if matched_case_id is None:
                continue

            matched_cases.add(matched_case_id)
            passed = result_map[matched_case_id]
            row[column_auto_test_result - 1].value = "Pass" if passed else "Fail"
            row[column_auto_test_result - 1].fill = green_fill if passed else red_fill
            row[column_auto_test_date - 1].value = test_date
            row[column_auto_test_version - 1].value = android_version

            if not passed:
                row[column_auto_test_result - 1].font = Font(bold=True)
                for k, v in fail_diff.items():
                    if k == matched_case_id:
                        row[column_diff_pic - 1].hyperlink = "file:///" + v
                        row[column_diff_pic - 1].value = "打开Diff文件超链接"
                        row[column_diff_pic - 1].font = Font(color="0000FF", underline="single")
                        border = Border(
                            left=Side(style='thin', color='000000'),
                            right=Side(style='thin', color='000000'),
                            top=Side(style='thin', color='000000'),
                            bottom=Side(style='thin', color='000000')
                        )
                        row[column_diff_pic - 1].border = border
                        break
                    # row[column_diff_pic - 1].hyperlink = "file:///D:/11/diff/25-08-26_16-13-07.png"
                    # row[column_diff_pic - 1].value = "打开Diff文件"
                    # row[column_diff_pic - 1].font = Font(color="0000FF", underline="single")
                    # border = Border(
                    #     left=Side(style='thin', color='000000'),
                    #     right=Side(style='thin', color='000000'),
                    #     top=Side(style='thin', color='000000'),
                    #     bottom=Side(style='thin', color='000000')
                    # )
                    # row[column_diff_pic - 1].border = border
                    # row[column_diff_pic - 1].style = "Hyperlink"

    if types == "all_func":
        # 动态查找列标题
        try:
            column_prerequisite_code = headers.index("前提代码") + 1
            column_prerequisite = headers.index("前提条件") + 1
            column_steps = headers.index("步骤描述") + 1
            column_automation = headers.index("自动化") + 1
            column_id = headers.index("编号") + 1
            column_res = headers.index("预期结果") + 1
            column_large_title = headers.index("需求大标题") + 1
            column_signame = headers.index("signame校准") + 1
            column_add_gap = headers.index("补充gap_sleep") + 1
            column_del_gap = headers.index("删除多余gap_sleep") + 1
            column_res_times = headers.index("结果次数校准") + 1
            column_test_result = headers.index("测试结果") + 1

        except ValueError:
            print("列标题中未找到'前提代码'或'自动化'，请检查 Excel 文件格式。")

        cnt = 1
        for row in sheet.iter_rows(min_row=2, values_only=False):  # 从第2行开始读取数据，不使用 values_only=True

            pass_case = []
            fail_case = []

            cnt += 1
            if cnt < start:
                continue
            if cnt == end:
                break

            id_cell = row[column_id - 1]
            case_id = id_cell.value

            result_cell = row[column_test_result - 1]
            result_value = result_cell.value
            for k, v in tests_result.items():
                if all(v.values()):
                    pass_case.append(k)
                else:
                    fail_case.append(k)

            for p in pass_case:
                if case_id == p:
                    row[column_test_result - 1].value = "Pass"
                    row[column_test_result - 1].fill = green_fill

            for f in fail_case:
                if case_id == f:
                    row[column_test_result - 1].value = "Fail"
                    row[column_test_result - 1].fill = red_fill

            cell = row[column_prerequisite_code - 1]  # 获取前提代码单元格
            prerequisite_code = cell.value  # 获取前提代码的值

            # 检查是否为合并单元格
            merged_cells = sheet.merged_cells.ranges  # 获取所有合并单元格的范围
            merged_range = None
            merged_ranges = []

            for mr in merged_cells:
                merged_ranges.append(str(mr))

            is_merged = False
            for merged_cell in merged_cells:
                if cell.coordinate in merged_cell:  # 如果当前单元格在合并单元格范围内
                    is_merged = True
                    merged_range = merged_cell
                    break

            # cell = row[column_prerequisite_code - 1]
            # prerequisite_code = cell.value

            pre_cell = row[column_prerequisite - 1]
            prerequisite = pre_cell.value

            # 预期结果
            test_result = []

            # res_cell = row[column_res - 1]
            # res = res_cell.value

            # 需求大标题
            requirement_large_title = row[column_large_title - 1]
            requirement_vaule = requirement_large_title.value

            # 测试步骤
            test_stepss = []
            if is_merged:
                step_start_row = merged_range.min_row
                step_end_row = merged_range.max_row
                target_light = ""
                for i in range(step_start_row, step_end_row + 1):
                    st = 0
                    step_merged = sheet.cell(row=i, column=column_steps).value
                    auto_merged = sheet.cell(row=i, column=column_automation).value
                    result_merged = sheet.cell(row=i, column=column_res).value
                    for k1, v1 in enumerate(auto_merged.split('\n')):
                        if v1 == "gap_sleep(3)" or v1 == "sleep(180)":
                            st += 1

                    for k2, v2 in enumerate(result_merged.split('\n')):
                        # if "闪烁" or "点亮" in result_merged.split('\n')[0]:
                        #     print(result_merged.split('\n')[0].split("灯")[0].split(".")[-1],"dengdeng")
                        #     target_light = result_merged.split('\n')[0].split("灯")[0].split(".")[-1] + "灯"
                        if "指示灯熄灭" in v2:
                            target_light = requirement_vaule.split(".")[-1]
                            v2 = v2.replace("指示灯", target_light)
                            sheet.cell(row=i, column=column_res).value = v2

                    if len(step_merged.split('\n')) > st:  # 步骤和代码不一致
                        test_stepss.append(step_merged)
                    elif len(step_merged.split('\n')) == st:  # 步骤和代码一致
                        for t1, t2 in enumerate(step_merged.split('\n')):
                            test_stepss.append(t2)
                        # for r1, r2 in enumerate(step_merged.split('\n')):
                        #     test_stepss.append(r2)
                    else:
                        pass
                        # print("非法数据，请重新校验")

                    # if len(result_merged.split('\n')) > st:  # 步骤和代码不一致
                    #     test_result.append(result_merged)
                    #
                    # elif len(result_merged.split('\n')) == st:  # 步骤和代码一致
                    #     for r1, r2 in enumerate(result_merged.split('\n')):
                    #         test_result.append(r2)
                    #     # for r1, r2 in enumerate(step_merged.split('\n')):
                    #     #     test_stepss.append(r2)
                    # else:
                    #     pass

                    # if step_merged is not None:
                    #     test_stepss.append(step_merged)
                steps = test_stepss

                # for i in range(step_start_row, step_end_row + 1):
                #     rt = 0
                #     result_merged = sheet.cell(row=i, column=column_res).value
                #     auto_merged = sheet.cell(row=i, column=column_automation).value

                #     if step_merged is not None:
                #         test_result.append(result_merged.split('\n'))
                # print(test_result, "合并的预期结果。。。")
                res = test_result
            else:
                test_steps = row[column_steps - 1]
                steps = test_steps.value

                res_cell = row[column_res - 1]
                res = res_cell.value

            # id_cell = row[column_id -1]
            # case_id = id_cell.value

            auto_cell = row[column_automation - 1]
            auto = auto_cell.value

            res_cell = row[column_res - 1]
            res = res_cell.value

            if auto is not None:
                if auto.split('\n')[-1] == "gap_sleep(3)":
                    row[column_add_gap - 1].value = "Yes"
                    # continue
                else:
                    row[column_add_gap - 1].value = "No"
                    new_data = auto + "\ngap_sleep(3)"
                    row[column_automation - 1].value = new_data
            else:
                print("空单元格。。。")
                continue
            gap_counter = 0
            # res_counter = res.count('.')
            if auto is not None:
                for i in auto.split('\n'):
                    if i == "gap_sleep(3)":
                        gap_counter += 1

            if res is not None:
                res_counter = res.count('.')
                if gap_counter == res_counter:
                    row[column_res_times - 1].value = "Yes"
                    row[column_res_times - 1].fill = green_fill
                else:
                    row[column_res_times - 1].value = "No"
                    row[column_res_times - 1].fill = red_fill
            else:
                print("结果为空。。。")

    workbook.save(excel_path)
    print("Excel表格测试结果写入完毕")


project_excel = {

    "byd": {'smoke': f"{app_path}/test_report/BYD/BYD快速冒烟测试自动化测试报告.xlsx",
            'all_func': "./test_report/BYD/BYD全功能测试结果.xlsx"},
    "d01": {'smoke': f"{app_path}/test_report/D01/D01快速冒烟测试自动化测试报告.xlsx",
            'all_func': "./test_report/D01/D01全功能测试结果.xlsx"},
    "N50": {'smoke': f"{app_path}/test_report/N50/N50快速冒烟测试自动化测试报告.xlsx",
            'all_func': f"{app_path}/test_report/N50/N50全功能测试结果.xlsx"},
    "N80": {'smoke': f"{app_path}/test_report/N80/N80快速冒烟测试自动化测试报告.xlsx",
            'all_func': f"{app_path}/test_report/N80/N80全功能测试结果.xlsx"},
    "N51": {'smoke': f"{app_path}/test_report/N51/N51快速冒烟测试自动化测试报告.xlsx",
            'all_func': f"{app_path}/test_report/N51/N51全功能测试结果.xlsx"},
    "T12A": {'smoke': f"{app_path}/test_report/T12A/T12A座舱自动化压力测试报告.xlsx",
             'all_func': f"{app_path}/test_report/T12A/T12A全功能测试结果.xlsx"},
    "T1V": {'smoke': f"{app_path}/test_report/T1V/T1V自动化冒烟测试报告.xlsx",
            'all_func': f"{app_path}/test_report/T1V/T1V全功能测试结果.xlsx"}
}


def _make_report_copy_path(template_path):
    """
    Create a timestamped report path next to the template file.
    """
    base_dir = os.path.dirname(template_path)
    stem, ext = os.path.splitext(os.path.basename(template_path))
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(base_dir, "generated")
    os.makedirs(report_dir, exist_ok=True)
    return os.path.join(report_dir, f"{stem}_{timestamp}{ext}")


def write_test_result_by_project(project, test_types, tests_result, fail_diff):
    try:
        for k, v in project_excel.items():
            for k1, v1 in v.items():
                if project == k:
                    if test_types == k1:
                        report_path = _make_report_copy_path(v1)
                        shutil.copy2(v1, report_path)
                        _write_test_result(test_types, 2, 80, tests_result, report_path, fail_diff)
                        return report_path
    except Exception as e:
        traceback.print_exc()
        print(f"写入测试结果时出错{e}")
    return None


if __name__ == "__main__":
    pass
    # excel_paths = "./test_report/D01/D01快速冒烟测试自动化测试报告.xlsx"
    # test_ret = {1: {'步骤1': False, '步骤2': False, '步骤3': True}, 2: {'步骤1': False, '步骤2': False, '步骤3': True},
    #             3: {'步骤1': True, '步骤2': True, '步骤3': True}, 4: {'步骤1': True, '步骤2': True, '步骤3': False},
    #             5: {'步骤1': True, '步骤2': True, '步骤3': False}, 6: {'步骤1': False, '步骤2': False, '步骤3': True},
    #             7: {'步骤1': True, '步骤2': True, '步骤3': True}, 8: {'步骤1': True, '步骤2': True, '步骤3': False},
    #             9: {'步骤1': True, '步骤2': False, '步骤3': False}, 10: {'步骤1': True, '步骤2': True, '步骤3': True},
    #             11: {'步骤1': False, '步骤2': False, '步骤3': True},
    #             12: {'步骤1': False, '步骤2': False, '步骤3': False}, 13: {'步骤1': True, '步骤2': True, '步骤3': True},
    #             14: {'步骤1': False, '步骤2': True, '步骤3': True}, 15: {'步骤1': True, '步骤2': True, '步骤3': True},
    #             16: {'步骤1': True, '步骤2': False, '步骤3': False},
    #             17: {'步骤1': False, '步骤2': True, '步骤3': False},
    #             18: {'步骤1': False, '步骤2': False, '步骤3': True},
    #             19: {'步骤1': False, '步骤2': False, '步骤3': True},
    #             20: {'步骤1': False, '步骤2': True, '步骤3': False},
    #             21: {'步骤1': False, '步骤2': True, '步骤3': False},
    #             22: {'步骤1': False, '步骤2': True, '步骤3': True}, 31: False, 32: False, 44: False, 45: False, 62: False}
    # test_ret1 = {31: False, 32: False, 44: True, 45: True, 62: True}
    # # write_test_result('smoke', 2, 65, test_ret1, excel_paths)
    # write_test_result_by_project("d01", "smoke", test_ret1, {31:"D:/11/diff/25-08-29_15-01-06.png", 32:"D:/11/diff/25-08-29_15-01-06.png"})
