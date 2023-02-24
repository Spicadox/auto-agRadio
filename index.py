import os.path
import os
import logging
import traceback
from datetime import datetime
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
import subprocess
import pytz
import time
import threading
from pathlib import Path

tz = pytz.timezone('Asia/Tokyo')
LOADING = True

# Set the list to contain the radio segments to only monitor and download.
# This is essentially a whitelist and can't be used with blacklisting. To only enable this whitelisting, set nonestop_monitor to False below
# 『hololive IDOL PROJECT presents ホロライブアイドル道ラジオ～私たちの歌をきけッ！』 毎週日曜日17：30～18：00
# 『星街すいせい・田所あずさ 平行線すくらんぶる』 毎週日曜17時〜
radio_list = ["hololive", "星街すいせい", "だいたいにじさんじのらじお", "平行線すくらんぶる", "Fate", "A&G ARTIST ZONE ▽▲TRiNITY▲▽ のTHE CATCH", "悠木碧のこしらえるラジオ"]


# Set to True to monitor and download every radio segment seperately and essentially enable just blacklisting radios.
# This is essentially a blacklist and can't be used with whitelisting
# If nonstop_monitor is true then all radio will be downloaded except the ones specified in the exclude_radio_list
nonstop_monitor = False
exclude_radio_list = ["放送休止"]

# Defaults to the current working directory
OUTPUT_PATH = ""


def loading_text():
    loading_string = "[INFO] Waiting for radio segment(s) "
    animation = ["     ", ".    ", "..   ", "...  ", ".... ", "....."]
    idx = 0
    while True:
        if LOADING:
            print(loading_string + animation[idx % len(animation)], end="\r")
            time.sleep(0.3)
            idx += 1
            if idx == 6:
                idx = 0


def submit_form():
    try:
        # Select the first option for gender
        gender_button_element = WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.NAME, "sex")))
        gender_button_element[0].click()
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Error with gender element", e)

    try:
        # Send a year value
        birth_year_button_element = WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.ID, "birth_year")))
        birth_year_button_element[0].send_keys(1999)
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Error with birth year element", e)

    try:
        # Select the first employment from the dropdown box
        job_button_element_select = Select(driver.find_element(By.NAME, "job"))
        job_button_element_select.select_by_value('1')
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Error with job element", e)

    try:
        # Click on the first location button
        environment_button_element = WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.NAME, "location")))
        environment_button_element[0].click()
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Error with environment element", e)

    try:
        # Click on the submit button
        submit_button_element = driver.find_element(By.CSS_SELECTOR, "input[type='button']")
        submit_button_element.click()
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Error with submit element", e)

    try:
        # Click on the OK button from the alert popup
        WebDriverWait(driver, 10).until(EC.alert_is_present())
        driver.switch_to.alert.accept()
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Error with ok element", e)


def sanitize_text(radio_info):
    # Replace double quotes with “ which is a Unicode character U+201C “, the LEFT DOUBLE QUOTATION MARK. Note: ” U+201D is a Right Double Quotation Mark
    # Replace < and > with unicode fullwidth less-than sign and fullwidth less-than sign
    # Replace : with unicode character U+A789 ꞉ which is a Modifier Letter Colon
    # Replace / with unicode character U+2215 ⁄ which is a unicode division slash
    # Replace ? with unicode character U+FF1F ？ which is a fullwidth question mark
    # Replace \ with unicode character U+29F5 ⧵ which is a Reverse Solidus Operator
    # Replace * with unicode character U+204E ⁎ which is a Low Asterisk
    # Replace | with unicode character U+23D0 ⏐ which is a Vertical Line Extension
    radio_info[0] = radio_info[0].replace('"', '“').replace("<", "＜").replace(">", "＞").replace(":", "꞉") \
        .replace("/", "∕").replace("?", "？").replace("\\", "⧵").replace("*", "⁎").replace("|", "⏐")
    radio_info[1] = radio_info[1].replace('"', '“').replace("<", "＜").replace(">", "＞").replace(":", "꞉") \
        .replace("/", "∕").replace("?", "？").replace("\\", "⧵").replace("*", "⁎").replace("|", "⏐")
    return tuple(radio_info)


def check_file(output_path, full_output_path):
    # Check if directory exist and if not create it
    Path(output_path).mkdir(parents=True, exist_ok=True)
    file_exist = os.path.isfile(full_output_path)
    return file_exist


def write_metadata_file(radio_info, date):
    title = radio_info[0].replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\\", "\\\\")
    with open("metadata.txt", "w", encoding='utf-8', newline='\n') as metadata_file:
        metadata_file.write(";FFMETADATA1")
        metadata_file.write(f"TITLE={title}\n")
        metadata_file.write(f"DATE={date[:4]}-{date[4:6]}-{date[6:8]}\n")

        comments = radio_info[1].replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\\", "\\\\").split("\n")
        counter = 1
        metadata_file.write("DESCRIPTION=")
        for comment in comments:
            metadata_file.write(comment)
            if counter < len(comments):
                metadata_file.write("\\" + "\n")
                metadata_file.write("\\" + "\n")
                counter += 1


def get_radio_info():
    p_name = ""
    p_text = ""

    while p_name == "":
        p_name_element = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.ID, "P_name")))
        p_name = p_name_element[0].text

        p_text_element = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.ID, "P_text")))
        p_text = p_text_element[0].text

    radio_info = [p_name, p_text]
    radio_info = sanitize_text(radio_info)
    return radio_info


def download(radio_info):
    file_exist = False
    date = datetime.now(tz=tz).strftime("%Y%m%d")
    # comment = radio_info[1].replace("\n", " ")
    # print(comment)
    filename = date + " - " + radio_info[0] + ".mkv"

    # Get output path and if it ends with backward slash then remove it
    if OUTPUT_PATH is not None and OUTPUT_PATH != "":
        output_path = OUTPUT_PATH
        if output_path[-1] == "\\":
            output_path = output_path[:-1]
    else:
        output_path = os.getcwd() + "\\"
    output_path = output_path + radio_info[0]
    full_output_path = output_path + "\\" + filename

    if check_file(output_path, full_output_path):
        filename = datetime.now(tz=tz).strftime("%Y%m%d%H%M") + " - " + radio_info[0] + ".mkv"
        full_output_path = output_path + "\\" + filename
        file_exist = True

    write_metadata_file(radio_info, date)

    command_list = ['ffmpeg', '-v', 'quiet', '-stats', '-re', '-i', 'https://www.uniqueradio.jp/agplayer5/hls/mbr-0.m3u8']
    command_list += ['-i', 'metadata.txt', '-map_metadata', '1']
    command_list += ['-c', 'copy', "-c:a", "aac", full_output_path]
    process = subprocess.Popen(command_list)
    print(" "*50, end="\r")
    print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {radio_info[0]} is now on the air")
    if file_exist:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | File already exist...renaming to: {filename}")
    return process


def monitor_radio():
    downloading_process = None
    found_radio = False
    previous_radio = get_radio_info()[0]
    global LOADING
    thread_name = ""
    while True:
        LOADING = downloading_process is None
        if thread_name == "":
            t1 = threading.Thread(target=loading_text)
            t1.start()
            thread_name = t1.name
        radio_info = get_radio_info()

        if nonstop_monitor:
            for radio in exclude_radio_list:
                if radio not in radio_info[0] and previous_radio == radio_info[0]:
                    found_radio = True
                    break
                elif previous_radio != radio_info[0] and downloading_process is not None:
                    found_radio = False
            previous_radio = radio_info[0]
        else:
            for radio in radio_list:
                if radio in radio_info[0] and previous_radio == radio_info[0]:
                    found_radio = True
                    break
                elif previous_radio != radio_info[0] and downloading_process is not None:
                    found_radio = False
            previous_radio = radio_info[0]

        if found_radio and downloading_process is None:
            downloading_process = download(radio_info)
        elif not found_radio and downloading_process is not None:
            downloading_process.terminate()
            print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Program has ended...")
            downloading_process = None
            found_radio = False
            try:
                os.remove("metadata.txt")
            except OSError:
                pass


if __name__ == "__main__":
    try:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Starting Program...")
        logging.getLogger('WDM').setLevel(logging.ERROR)
        os.environ['WDM_LOG'] = "false"
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--mute-audio')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.81 Safari/537.36")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    except WebDriverException as driverError:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {driverError}")

    try:
        driver.get("https://www.uniqueradio.jp/agplayer5/player.php")
        data = driver.page_source
        if "ご利用登録" in data:
            submit_form()
        driver.refresh()
        monitor_radio()
    except Exception:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {traceback.format_exc()}")
        try:
            os.remove("metadata.txt")
        except OSError:
            pass
