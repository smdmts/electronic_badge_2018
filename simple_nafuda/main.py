#!/usr/bin/python3.5
#
# simple nafuda slide show
#
# for development.
# $ export PSEUDO_EPD_MODE=1
# $ python main.py
#
# Copyright (C) Aug 4 2018, Junichi Ishida <uzulla@himitsukichi.com>
#
# LICENSE : MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
# to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
#  the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import os
import sys
import time
import re
import qrcode
import hashlib
import requests
import json
import traceback
from PIL import Image

BASE_URL = "https://eb2018.builderscon.io/"
# BASE_URL = "http://u.cfe.jp/"

sys.path.append(os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + '/../lib'))

from nafuda import Nafuda

if "IMG_DIR" in os.environ:
    IMG_DIR = os.environ["IMG_DIR"]
else:
    if os.path.isdir('/mnt/virtual_sd/img'):
        IMG_DIR = '/mnt/virtual_sd/img'
    else:
        # virtual sdがない時（開発時など）用
        IMG_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + '/img')

CLOUD_JSON_CACHE_PATH = IMG_DIR + "/cloud.json"
CLOUD_QR_CODE_FILE_NAME = "__CONVERT_TO_QR__.png"
CLOUD_QR_CODE_FILE_PATH = IMG_DIR + "/" + CLOUD_QR_CODE_FILE_NAME


def main():
    result = load_settings_from_cloud()

    if result is not True:
        # 場合によってはエラーかもしれないけど、とまると困るので続行させる
        print(result)

    # load image file list
    file_list = []
    for file in os.listdir(IMG_DIR):
        # get (png|jpg|jpeg|gif) files. and skip dot files.
        if re.search('^[^\.].*\.(png|jpg|jpeg|gif)', file, re.IGNORECASE):
            file_list.append(file)

    if len(file_list) == 0:
        print('no image, exit.')
        sys.exit(0)

    file_list.sort()

    print(file_list)

    nafuda = Nafuda()

    while True:
        for file in file_list:
            if file == CLOUD_QR_CODE_FILE_NAME:
                # QRコードを合成して表示
                base_image = Image.open(CLOUD_QR_CODE_FILE_PATH)
                qr_img = get_control_url_qrcode_img()
                base_image.paste(qr_img, (10, 10))
                nafuda.draw_image_buffer(base_image, orientation=90)
                if "PSEUDO_EPD_MODE" in os.environ:
                    # guard for img bomb.
                    time.sleep(3)
                continue

            try:
                nafuda.draw_image_file(IMG_DIR + '/' + file, 90)

            except OSError:
                # maybe, the file is not correct image file.
                print("load image fail: " + file)

            if "PSEUDO_EPD_MODE" in os.environ:
                # guard for img bomb.
                time.sleep(3)

            # 一枚しか画像がなければ、スライドショーする意味がないので終了
            if len(file_list) == 1:
                exit(0)


def load_settings_from_cloud():
    # QRコードに置換する画像がなければ、クラウド機能は不要と判断して実行しない
    # https://server/{SHA2}/json settings
    # https://server/{SHA2}/ UI
    # https://server/bc2018/{SHA2}/[0-9].(png|jpg|gif...) imgs
    if os.path.isfile(CLOUD_QR_CODE_FILE_PATH):
        try:
            # 設定JSONをサーバーから取得試行
            r = requests.get(get_control_url() + "json")
            if r.status_code != 200:
                return "json not found"

            json_str = r.text

            data = json.loads(json_str)
            img_list = data['list']
            if not isinstance(img_list, list):
                return "maybe invalid json"

            if len(img_list) == 0:
                # 空の場合はなにもしない
                return "empty list"

            # 過去のJSONがあれば、更新があるか確認
            if os.path.isfile(CLOUD_JSON_CACHE_PATH):
                with open(CLOUD_JSON_CACHE_PATH, "r") as jc:
                    cached_json = jc.read()
                    if cached_json == json_str:
                        return "json not updated"

            # rwで再マウント
            if os.path.isfile("/usr/bin/mount_vsd_rw"):
                if os.system('/usr/bin/mount_vsd_rw') != 0:
                    return "mount_vsd_rw fail."

            # clean up img dir
            file_list_to_rm = os.listdir(IMG_DIR)
            for f in file_list_to_rm:
                p = IMG_DIR + "/" + f
                if os.path.isfile(p):
                    if re.search('^[^\.].*\.(png|jpg|jpeg|gif)', p, re.IGNORECASE):
                        if f != CLOUD_QR_CODE_FILE_NAME:
                            os.remove(p)

            # 画像をDLして保存
            id = 1
            for img in img_list:
                root, ext = os.path.splitext(img)
                get_and_save_file(get_img_url_base() + "/" + img, IMG_DIR + "/" + str(id) + ext)
                id = id + 1

            # save json
            with open(CLOUD_JSON_CACHE_PATH, "w") as jc:
                jc.write(json_str)

            # roで再マウント
            if os.path.isfile("/usr/bin/mount_vsd_ro"):
                if os.system('/usr/bin/mount_vsd_ro') != 0:
                    return "mount_vsd_ro fail."

            return True

        except:
            # 止まられると困る！
            traceback.print_exc()
            return False


def get_nafuda_id():
    h_path = '/mnt/virtual_sd/default_hostname.txt'
    p_path = '/mnt/virtual_sd/default_passwd.txt'

    if not os.path.isfile(h_path) or not os.path.isfile(p_path):
        return False

    try:
        hostname = open(h_path).read(128).encode('UTF-8')
        passwd = open(p_path).read(128).encode('UTF-8')

        hash = hashlib.sha256(hostname + passwd).hexdigest()
        # print(hash)

    except OSError:
        return False

    return hash


def get_img_url_base():
    return BASE_URL + "/bc2018/" + get_nafuda_id() + "/"


def get_control_url():
    return BASE_URL + get_nafuda_id() + "/"


def get_control_url_qrcode_img():
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=4,
    )

    qr.add_data(get_control_url())
    qr.make(fit=True)
    # print(qr.size)
    return qr.make_image(fill_color="black", back_color="white")


def get_and_save_file(url, file_path):
    r = requests.get(url, stream=True)
    with open(file_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                f.flush()


if __name__ == '__main__':
    main()
