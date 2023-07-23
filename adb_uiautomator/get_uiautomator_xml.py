import os
import tempfile

from adb_uiautomator.utils import Utils, AdbError
from lxml import etree

from adb_uiautomator.logger_config import logger


def check_file_exists_in_sdcard(udid, file_name):
    utils = Utils(udid)
    rst = utils.qucik_shell(f"ls {file_name}")
    return rst


def init_adb_auto(udid):
    utils = Utils(udid)
    dict = {
        "app.apk": "hank.dump_hierarchy",
        "android_test.apk": "hank.dump_hierarchy.test",
    }
    rst = utils.qucik_shell("pm list packages hank.dump_hierarchy")
    if rst.find("not found") > 0:
        raise AdbError(rst)

    for i in ["android_test.apk", "app.apk"]:
        if f"package:{dict.get(i)}" not in rst:
            lib_path = os.path.dirname(__file__) + f"\libs\{i}"
            utils.cmd(f"install {lib_path}")
            logger.debug(f"adb install {i} successfully")

    logger.debug("adb uiautomator was initialized successfully")


def dump_ui_xml(udid, reload):
    utils = Utils(udid)
    if check_xml_exists(udid) and reload is False:
        logger.debug(f"A local file already exists, And the existing files will be read first")
    else:
        commands = f"""am instrument -w -r -e class hank.dump_hierarchy.HierarchyTest hank.dump_hierarchy.test/androidx.test.runner.AndroidJUnitRunner"""
        utils.qucik_shell(commands)
        logger.debug("adb uiautomator dump successfully")


def check_xml_exists(udid):
    temp_folder = tempfile.gettempdir()
    path = temp_folder + f"/{udid}_ui.xml"
    return os.path.exists(path)


def remove_ui_xml(udid):
    if check_xml_exists(udid):
        temp_folder = tempfile.gettempdir()
        path = temp_folder + f"/{udid}_ui.xml"
        os.remove(path)


def pull_ui_xml_to_temp_dir(udid):
    utils = Utils(udid)
    temp_file = tempfile.gettempdir() + f"/{udid}_ui.xml"
    command = f'pull /storage/emulated/0/Android/data/hank.dump_hierarchy/cache/2.xml {temp_file}'
    utils.cmd(command)
    return temp_file


def get_root_node(udid, reload=False):
    import lxml.etree as ET
    def custom_matches(_, text, pattern):
        import re
        text = str(text)
        return re.search(pattern, text) is not None

    # 创建自定义函数注册器
    custom_functions = etree.FunctionNamespace(None)

    # 注册自定义函数
    custom_functions['matches'] = custom_matches
    for i in range(5):
        try:
            dump_ui_xml(udid, reload)
            break
        except AdbError:
            logger.debug(f"init fail, retry {i + 1} times")

    xml_file_path = pull_ui_xml_to_temp_dir(udid)
    # 解析XML文件
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    return root


init_adb_auto("xxx")