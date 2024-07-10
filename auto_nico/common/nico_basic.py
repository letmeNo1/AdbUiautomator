import json
import time

import os

import cv2
from auto_nico.common.kmeans_run import kmeans_run
from auto_nico.android.adb_utils import AdbUtils
from lxml.etree import _Element

from auto_nico.ios.XCUIElementType import get_value_by_element_type
from typing import Union

import tempfile

from auto_nico.common.logger_config import logger
from auto_nico.common.send_request import send_tcp_request

import lxml.etree as ET

from auto_nico.ios.tools.format_converter import converter

from auto_nico.common.runtime_cache import RunningCache

from auto_nico.android.tools.format_converter import convert_xpath


class UIStructureError(Exception):
    pass


class NicoBasic:
    def __init__(self, udid, **query):
        self.udid = udid
        self.query = query

    def _dump_ui_xml(self, configuration):
        response = None
        port = RunningCache(self.udid).get_current_running_port()
        for _ in range(5):
            if "NicoAndroid" in self.__class__.__name__:
                compressed = configuration.get("compressed")
                response = send_tcp_request(port, f"dump:{str(compressed).lower()}").replace("class=",
                                                                                             "class_name=").replace(
                    "resource-id=", "id=").replace("content-desc=", "content_desc=")
            elif "NicoIOS" in self.__class__.__name__:
                package_name = configuration.get("package_name")
                response = send_tcp_request(port, f"dump_tree:{package_name}")
                response = converter(response)

            if "<hierarchy" in response and "</hierarchy>" in response:
                # logger.debug(f"{self.udid}'s UI tree is dump success!!!")
                runtime_cache = RunningCache(self.udid)
                runtime_cache.clear_current_cache_ui_tree()
                runtime_cache.set_current_cache_ui_tree(response)
                root = ET.fromstring(response.encode('utf-8'))
                return root

            else:
                logger.debug(f"{self.udid}'s UI tree dump fail, retrying...")
                time.sleep(1)
                if "NicoAndroid" in self.__class__.__name__:
                    adb_utils = AdbUtils(self.udid)
                    adb_utils.restart_test_server(port)
        raise UIStructureError(f"{self.udid}'s UI tree dump fail")

    def _get_root_node(self, configuration: dict):
        """
        get the root node of the element tree
        @param configuration: The configuration of the platform
        @param udid: The device ID
        @param port: The port number of automation server
        @param force_reload: Whether to force reload the element tree, default is False
        @return: The root node of the element tree
        """
        ui_change_status = RunningCache(self.udid).get_ui_change_status()
        # logger.debug(f"ui tree change is {ui_change_status}")

        if not ui_change_status:
            # logger.debug(f"{self.udid}'s UI no change. There is no need to dump again!!")
            return RunningCache(self.udid).get_current_cache_ui_tree()
        else:
            # logger.debug(f"{self.udid}'s UI is change. dump again!!")
            return self._dump_ui_xml(configuration)

    def __find_function_by_image(self, image_path, threshold, algorithms):
        platform = self.__class__.__name__,
        if "NicoAndroidElement" in platform:
            adb_utils = AdbUtils(self.udid)
            original_image = adb_utils.get_image_object(100)
            target_image = cv2.imread(image_path)
            if threshold is None:
                threshold = 0.8
            if algorithms is None:
                algorithms = "SIFT"
            x, y, h, w = kmeans_run(target_image, original_image, threshold, algorithms)
            if x is not None:
                return {"bounds": f"[{x},{y}][{w},{h}]"}
            else:
                return None

    def __find_function_by_xml(self, query, multi=False, index=0, return_all=False) -> Union[_Element, None, list]:
        def __find_element_by_query_by_xml(root, query) -> Union[list, None]:
            xpath_expression = ".//*"
            conditions = []
            is_re = False
            for attribute, value in query.items():
                if attribute == "compressed":
                    pass
                elif attribute == "xpath":
                    xpath_expression = convert_xpath(value)
                    matching_elements = root.xpath(xpath_expression)
                else:
                    if attribute.find("_matches") > 0:
                        is_re = True
                        attribute = attribute.replace("_matches", "")
                        condition = f"re:match(@{attribute},'{value}')"
                    elif attribute.find("_contains") > 0:
                        attribute = attribute.replace("_contains", "")
                        condition = f"contains(@{attribute},'{value}')"
                    else:
                        condition = f"@{attribute}='{value}'"
                    conditions.append(condition)
                    if conditions:
                        xpath_expression += "[" + " and ".join(conditions) + "]"
                    if is_re:
                        ns = {"re": "http://exslt.org/regular-expressions"}
                        matching_elements = root.xpath(xpath_expression, namespaces=ns)
                    else:
                        matching_elements = root.xpath(xpath_expression)
            if len(matching_elements) == 0:
                return None
            else:
                return matching_elements

        # logger.debug(f"{self.udid}'s UI tree is dumping!!")
        if query.get("compressed") is not None:
            compressed = query.get("compressed")
        else:
            compressed = True
        configuration = {
            "platform": self.__class__.__name__,
            "compressed": compressed,
            "package_name": RunningCache(self.udid).get_current_running_package()
        }
        root = self._get_root_node(configuration)
        found_rst = __find_element_by_query_by_xml(root, query)
        if found_rst is not None:
            if return_all is True:
                logger.debug(f"Found element by {query}")
                return found_rst
            if multi is True:
                logger.debug(f"Found element by {query}")
                return found_rst[index]
            else:
                logger.debug(f"Found element by {query}")
                return found_rst[0]
        return None

    def __find_element_by_query_for_ios(self, query, return_all=False) -> Union[dict, None]:
        port = RunningCache(self.udid).get_current_running_port()
        package_name = RunningCache(self.udid).get_current_running_package()
        NSPredicate_list = []
        for attribute, value in query.items():
            if attribute == "xpath":
                xpath_expression = value
                matching_element = send_tcp_request(port,
                                                    f"find_element_by_query:{package_name}:xpath:{xpath_expression}")
                if matching_element == "":
                    return None
                logger.debug(f"found element: {matching_element}")
                return json.loads(matching_element)
            elif attribute == "custom":
                if return_all:
                    matching_element = send_tcp_request(port,
                                                        f"find_elements_by_query:{package_name}:predicate:{value}")
                else:
                    matching_element = send_tcp_request(port,
                                                        f"find_element_by_query:{package_name}:predicate:{value}")
                if matching_element == "":
                    return None
                logger.debug(f"found element: {matching_element}")
                return json.loads(matching_element)
            else:
                if attribute.find("_contains") > 0:
                    if attribute == "text_contains":
                        condition = f'''label CONTAINS "{value}" OR title CONTAINS "{value}"'''
                    else:
                        attribute = attribute.replace("_contains", "")
                        condition = f"{attribute} CONTAINS {value}"
                else:
                    if attribute == "text":
                        condition = f'''label == "{value}" OR title == "{value}"'''
                    elif attribute == "class_name":
                        condition = f'''elementType == {get_value_by_element_type(value)}'''
                    else:
                        condition = f'''{attribute} == "{value}"'''
                NSPredicate_list.append(condition)
        NSPredicate = " AND ".join(NSPredicate_list)
        if return_all:
            matching_elements = send_tcp_request(port,
                                                 f"find_elements_by_query:{package_name}:predicate:{NSPredicate}")
            return json.loads(f"[{matching_elements}]")

        else:
            matching_element = send_tcp_request(port,
                                                f"find_element_by_query:{package_name}:predicate:{NSPredicate}")
            if matching_element == "":
                return None
        logger.debug(f"found element: {matching_element}")
        return json.loads(matching_element)

    def _find_function(self, query, use_xml=False) -> Union[dict, _Element]:
        platform = self.__class__.__name__,
        if query.get("image") is not None:
            image_path = query.get("image")
            threshold = query.get("threshold")
            algorithms = query.get("algorithms")
            found_element = self.__find_function_by_image(image_path, threshold, algorithms)
        elif "NicoAndroid" in str(platform) or use_xml:
            found_element = self.__find_function_by_xml(query)
        elif "NicoIOS" in str(platform):
            found_element = self.__find_element_by_query_for_ios(query)
        else:
            raise Exception("Unsupported platform")
        return found_element

    def _find_all_function(self, query):
        platform = self.__class__.__name__,
        element_list = []

        if "NicoAndroidElement" in platform:
            element_list = self.__find_function_by_xml(query, return_all=True)
        elif "NicoIOSElement" in platform:
            element_list = self.__find_element_by_query_for_ios(query, return_all=True)
        return element_list

    def __wait_function(self, timeout, wait_disappear, query):
        time_started_sec = time.time()
        query_string = list(query.values())[0]
        query_method = list(query.keys())[0]
        while time.time() < time_started_sec + timeout:
            found_node = self._find_function(query)
            if wait_disappear:
                if found_node is None:
                    time.time() - time_started_sec
                    return 1
                else:
                    RunningCache(self.udid).clear_current_cache_ui_tree()
            else:
                if found_node is not None:
                    time.time() - time_started_sec
                    return 1
                else:
                    RunningCache(self.udid).clear_current_cache_ui_tree()

        if wait_disappear:
            error = "Can't wait element/elements disappear in %s s by %s = %s" % (timeout, query_method, query_string)
        else:
            error = "Can't find element/elements in %s s by %s = %s" % (timeout, query_method, query_string)
        raise TimeoutError(error)

    def wait_for_appearance(self, timeout=10, force_reload=False):
        query_string = list(self.query.values())[0]
        query_method = list(self.query.keys())[0]
        logger.debug(f"Waiting element appearance by {query_method} = {query_string}")
        self.__wait_function(timeout, False, self.query)

    def wait_for_disappearance(self, timeout=10, force_reload=False):
        query_string = list(self.query.values())[0]
        query_method = list(self.query.keys())[0]
        logger.debug(f"Waiting element disappear by {query_method} = {query_string}")

        self.__wait_function(timeout, True, self.query)

    def wait_for_any(self, *any, timeout=10):
        find_times = 0
        query_list = []
        for item in any[0]:
            query_list.append(item.query)
        time_started_sec = time.time()
        while time.time() < time_started_sec + timeout:
            for index, query in enumerate(query_list):
                query_string = list(query.values())[0]
                query_method = list(query.keys())[0]
                found_node = self._find_function(query)
                if found_node is not None:
                    time.time() - time_started_sec
                    logger.debug(f"Found element by {index}. {query_method} = {query_string}")
                    return index
                else:
                    RunningCache(self.udid).clear_current_cache_ui_tree()
            find_times += 1
            if find_times == 1:
                logger.debug(f"no found any, try again")
        error = "Can't find element/elements in %s s by %s = %s" % (timeout, query_method, query_string)
        RunningCache(self.udid).set_action_was_taken(False)
        raise TimeoutError(error)

    def exists(self,timeout = None):
        query_string = list(self.query.values())[0]
        query_method = list(self.query.keys())[0]
        logger.debug(f"checking element is exists by {query_method}={query_string}...")
        rst = self._find_function(self.query) is not None
        if timeout is not None:
            time_started_sec = time.time()
            while time.time() < time_started_sec + timeout:
                if rst:
                    return True
                else:
                    RunningCache(self.udid).clear_current_cache_ui_tree()
                    rst = self._find_function(self.query) is not None
            return False
        return rst

    def get_root_xml(self, compressed):
        configuration = {
            "platform": self.__class__.__name__,
            "compressed": compressed,
        }
        self._get_root_node(configuration)
        temp_folder = os.path.join(tempfile.gettempdir(), f"{self.udid}_ui.xml")
        os.startfile(temp_folder)
