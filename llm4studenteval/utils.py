import json
import time
import base64
import urllib
import requests
from io import BytesIO

from keys import *

model_name = "GPT-4"

def get_access_token():
    """
    使用 AK，SK 生成鉴权签名（Access Token）
    :return: access_token，或是None(如果错误)
    """
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {"grant_type": "client_credentials", "client_id": BAIDU_API_KEY, "client_secret": BAIDU_SECRET_KEY}
    return str(requests.post(url, params=params).json().get("access_token"))

def get_file_content_as_base64(img):
    """
    获取文件base64编码
    :param path: 文件路径
    :param urlencoded: 是否对结果进行urlencoded 
    :return: base64编码信息
    """
    buffered = BytesIO()
    img.save(buffered, format="JPEG")
    content = base64.b64encode(buffered.getvalue()).decode("utf8")
    content = urllib.parse.quote_plus(content)
    # print(content)
    return content

new_data = []

def llm_evaluation(system_prompt, profile, temperature = 0.1, top_p = 0.3):
    url = OPENAI_API_BASE + "/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": OPENAI_API_KEY
    }

    data = {
        "model": "gpt-4",
        "messages": [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(profile)}],
        # "max_tokens": 4096,
        "temperature": temperature,
        'top_p': top_p,
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data)).json()
        response = response['choices'][0]['message']['content']
        time.sleep(3)
        return response
    except Exception as e:
        print(e)
        time.sleep(3)

def vlm_completion(img, text_prompt, temperature = 0.1, top_p = 0.3):
    url = OPENAI_API_BASE + "/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": OPENAI_API_KEY
    }

    buffer = BytesIO()
    img.save(buffer, format="jpeg")
    base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
    image_uri = f"data:image/jpeg;base64,{base64_image}"

    messages = [{"role": "user",
                 "content": [
                    {"type": "text", "text": text_prompt},
                    {"type": "image_url", "image_url": {"url": image_uri}},
                    ],
                }]
    
    data = {
        "model": "gpt-4",
        "messages": messages,
        # "max_tokens": 4096,
        "temperature": temperature,
        'top_p': top_p,
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data)).json()
        response = response['choices'][0]['message']['content']
        time.sleep(3)
        return response
    except Exception as e:
        print(e)
        time.sleep(3)


def baidu_text_ocr(img, max_attempts = 5):
    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token=" + get_access_token()

    payload=f'image={get_file_content_as_base64(img)}&detect_direction=false&paragraph=false&probability=false'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }

    attempt = 0

    while attempt < max_attempts:
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            response.raise_for_status()  # Raise an HTTPError if the response was an HTTP error
            time.sleep(2)
            try:
                refined_text = [x["words"] for x in response.json()["words_result"]]
                return refined_text
            except:
                attempt += 1
                pass
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            attempt += 1
            if attempt < max_attempts:
                time.sleep(60)  # wait for 1 minute before retrying

    time.sleep(2)
    # print(response.text)
    return f"No data"

def baidu_table_ocr(img, max_try = 3):
    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/table?access_token=" + get_access_token()
        
    payload=f'image={get_file_content_as_base64(img)}&cell_contents=false&return_excel=false'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    try_count = 0
    ocr_status = False
    while try_count < max_try:
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            raw_response =  response.json()
            if 'tables_result' in raw_response.keys():
                ocr_result = raw_response['tables_result'][0]
                try_count = max_try
                ocr_status = True
            else:
                ocr_result = raw_response
                try_count += 1
        except Exception as e:
            ocr_result = str(e)
            try_count += 1

    return ocr_status, ocr_result

def table_ocr_result_to_markdown(ocr_data):
    # Extracting text from the 'header'
    header_info = ""
    if 'header' in ocr_data:
        header_lines = [item['words'] for item in ocr_data['header']]
        header_info = "\n".join(header_lines).strip()
    
    # Extracting headers for the Markdown table from the 'body'
    headers = []
    for header in ocr_data['body']:
        if header['row_start'] == 0:
            headers.append(header['words'].replace('\n', ' '))
    
    # Create the Markdown table header row
    markdown_table = "| " + " | ".join(headers) + " |\n"
    markdown_table += "| " + " | ".join(['---'] * len(headers)) + " |\n"
    
    # Extract the body rows
    row_data = {}
    for cell in ocr_data['body']:
        row_start = cell['row_start']
        col_start = cell['col_start']
        words = cell['words'].replace('\n', ' ')
        if row_start not in row_data:
            row_data[row_start] = {}
        row_data[row_start][col_start] = words

    # Sort rows and columns to build the table content
    max_col = max(cell['col_end'] for cell in ocr_data['body'] if cell['row_start'] > 0)
    for row in sorted(row_data.keys()):
        if row > 0:  # Skip the header row
            row_cells = []
            for col in range(max_col + 1):
                row_cells.append(row_data[row].get(col, ''))
            markdown_table += "| " + " | ".join(row_cells) + " |\n"
    
    # Combine header info and markdown table
    result = ""
    if header_info:
        result += f"### Transcript header:\n{header_info}\n\n"
    result += "### Transcript detail:\n" + markdown_table
    return [result]