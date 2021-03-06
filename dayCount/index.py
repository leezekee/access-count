# -*- coding: utf8 -*-
import logging
import re
import sys
import json
import os
import datetime


from qcloud_cos import CosConfig
from qcloud_cos import CosServiceError
from qcloud_cos import CosS3Client
from qcloud_cos.cos_threadpool import SimpleThreadPool


# 正常情况日志级别使用INFO，需要定位时可以修改为DEBUG，此时SDK会打印和服务端的通信信息
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# 设置用户属性, 包括 secret_id, secret_key, region等。Appid 已在CosConfig中移除，请在参数 Bucket 中带上 Appid。Bucket 由 BucketName-Appid 组成
secret_id = ''     # 替换为用户的 SecretId，请登录访问管理控制台进行查看和管理，https://console.cloud.tencent.com/cam/capi
secret_key = ''   # 替换为用户的 SecretKey，请登录访问管理控制台进行查看和管理，https://console.cloud.tencent.com/cam/capi
region = ''      # 替换为用户的 region，已创建桶归属的region可以在控制台查看，https://console.cloud.tencent.com/cos5/bucket
                            # COS支持的所有region列表参见https://cloud.tencent.com/document/product/436/6224
token = None               # 如果使用永久密钥不需要填入token，如果使用临时密钥需要填入，临时密钥生成和使用指引参见https://cloud.tencent.com/document/product/436/14048
scheme = 'https'           # 指定使用 http/https 协议来访问 COS，默认为 https，可不填

config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Token=token, Scheme=scheme)
client = CosS3Client(config)
count = 0

# 用户的 bucket 信息
test_bucket = ''
start_prefix = 'cos-access-log/'
# 对象存储依赖 分隔符 '/' 来模拟目录语义，
# 使用默认的空分隔符可以列出目录下面的所有子节点，实现类似本地目录递归的效果,
# 如果 delimiter 设置为 "/"，则需要在程序里递归处理子目录
delimiter = ''


# 获取当前时间
today = datetime.date.today()
year = str(today.year)
if today.month < 10:
    month = "0" + str(today.month)
else:
    month = str(today.month)
if today.day < 10:
    day = "0" + str(today.day)
else:
    day = str(today.day)


# 需要检索的文件名称
files_count = 'index.md'
# json的云端路径
json_file_path = "/day-logs/" + year + "-" + month + "-" + day  + "-log.json"
json_dest_file_path = "/tmp/day-logs/" + year + "-" + month + "-" + day  + "-log.json"


# 列出当前目录子节点，返回所有子节点信息
def listCurrentDir(prefix):
    file_infos = []
    sub_dirs = []
    marker = ""
    count = 1
    while True:
        response = client.list_objects(test_bucket, prefix, delimiter, marker)
        # 调试输出
        # json_object = json.dumps(response, indent=4)
        # print(count, " =======================================")
        # print(json_object)
        count += 1

        if "CommonPrefixes" in response:
            common_prefixes = response.get("CommonPrefixes")
            sub_dirs.extend(common_prefixes)

        if "Contents" in response:
            contents = response.get("Contents")
            file_infos.extend(contents)

        if "NextMarker" in response.keys():
            marker = response["NextMarker"]
        else:
            break

    # print("=======================================================")

    # 如果 delimiter 设置为 "/"，则需要进行递归处理子目录，
    # sorted(sub_dirs, key=lambda sub_dir: sub_dir["Prefix"])
    # for sub_dir in sub_dirs:
    #     print(sub_dir)
    #     sub_dir_files = listCurrentDir(sub_dir["Prefix"])
    #     file_infos.extend(sub_dir_files)

    # print("=======================================================")

    sorted(file_infos, key=lambda file_info: file_info["Key"])
    # for file in file_infos:
    #     print(file)
    return file_infos


# 下载文件到本地目录，如果本地目录已经有同名文件则会被覆盖；
# 如果目录结构不存在，则会创建和对象存储一样的目录结构
def downLoadFiles(file_infos):
    
    localDir = "/tmp/"

    pool = SimpleThreadPool()
    for file in file_infos:
        # 文件下载 获取文件到本地
        file_cos_key = file
        localName = localDir + file_cos_key

        # 如果本地目录结构不存在，递归创建
        if not os.path.exists(os.path.dirname(localName)):
            os.makedirs(os.path.dirname(localName))

        # skip dir, no need to download it
        if str(localName).endswith("/"):
            continue

        # 实际下载文件
        # 使用线程池方式
        pool.add_task(client.download_file, test_bucket, file_cos_key, localName)

        # 简单下载方式
        # response = client.get_object(
        #     Bucket=test_bucket,
        #     Key=file_cos_key,
        # )
        # response['Body'].get_stream_to_file(localName)

    pool.wait_completion()
    print("Download files finished.")
    print("Download", len(file_infos), "files this time")
    return None


# 功能封装，下载对象存储上面的一个目录到本地磁盘
def downLoadDirFromCos(prefix):
    global file_infos

    try:
        start_prefix = prefix + year + "/" + month + "/" + day + "/"    # 云端目录
        # dest_file_path = "/tmp/cos-access-log/" + year + "/" + month + "/" + day + "/"    # 本地目录
        qcloud_files = listCurrentDir(start_prefix) # 获取云端目录下的文件
        file_infos = []    # 要下载的文件列表
        for file in qcloud_files:
            # file['Key'] = file['Key'].replace(start_prefix, '')
            file_infos.append(file['Key'])
        # print(file_infos)
        # print("exists_files:",len(exists_files))

    except CosServiceError as e:
        print(e.get_origin_msg())
        print(e.get_digest_msg())
        print(e.get_status_code())
        print(e.get_error_code())
        print(e.get_error_msg())
        print(e.get_resource_location())
        print(e.get_trace_id())
        print(e.get_request_id())

    downLoadFiles(file_infos)
    return None


# 上传文件到对象存储
def uploadAccessFile(cloud_file_path, local_file_path):
    client.upload_file(
        Bucket=test_bucket,
        Key=cloud_file_path,
        LocalFilePath=local_file_path,
        EnableMD5=False,
        progress_callback=None
    )


# 进行访问量统计
def accessCount(file_infos):
    # if rule == "all":
    #     dest_file_path = "./tmp/"
    # else:

    dest_file_path = "/tmp/cos-access-log/" + year + "/" + month + "/" + day + "/"
    day_count_files = {}
    for roots, dirs, files in os.walk(dest_file_path):
        for file in files:
            with open(os.path.join(roots, file), 'r') as f_read:
                if file in file_infos:
                    for line in f_read:
                        line = line.split(' ')
                        try:
                            if files_count in line[11]:
                                if '"' in line[11]:
                                    line[11] = eval(line[11])
                                # 日访问量统计
                                if line[11] in day_count_files.keys():
                                    day_count_files[line[11]] += 1
                                else:
                                    day_count_files[line[11]] = 1
                        except:
                            print("error file name:", file)
    
    os.makedirs('/tmp/day-logs')
    with open(json_dest_file_path, "w") as f:
        json.dump(day_count_files, f, indent=4)


def main_handler(event, context):
    downLoadDirFromCos(start_prefix)
    # print("main::file_infos:", file_infos)
    accessCount(file_infos)
    print(file_infos)
    uploadAccessFile(json_file_path, json_dest_file_path)
    return "Count Complete"


if __name__ == "__main__":
    main_handler(None, None)