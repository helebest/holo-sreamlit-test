import os
import io
import re
import time
import base64
from tempfile import NamedTemporaryFile
from hashlib import md5
from typing import Tuple
import streamlit as st
from openai import OpenAI
from streamlit.logger import get_logger
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

LOGGER = get_logger(__name__)
FILE_STORE = './data'

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Set up the Streamlit page with a title and icon
st.set_page_config(page_title="你的AI助理", layout="wide", page_icon=":speech_balloon:")

# Set a default model
if "openai_model" not in st.session_state:
    st.session_state.openai_model = os.getenv('MODEL_NAME')

if 'index' not in st.session_state:
    st.session_state.index = 0

if 'file_id_list' not in st.session_state:
    st.session_state.file_id_list = []

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []


def check_and_upload(ufile):
    file_prefix, file_suffix = os.path.splitext(ufile.name)
    file_bytes = ufile.read()
    md5sum = md5(file_bytes).hexdigest()
    existed = len(list(filter(lambda x: x[2] == md5sum, st.session_state.file_id_list)))
    if existed == 0:
        with NamedTemporaryFile(dir=FILE_STORE, prefix=file_prefix, suffix=file_suffix) as f:
            f.write(file_bytes)
            f.flush()
            response = client.files.create(file=open(f.name, 'rb'), purpose="assistants")
            st.session_state.file_id_list.append((response.id, ufile.name, md5sum))
        LOGGER.info(f'uploaded file: {ufile.name} with id={response.id} and md5={md5sum}')
    else:
        LOGGER.info(f'uploaded file: {ufile.name} already existed')


def download_file(fileId: str, fileName: str = 'download.csv') -> Tuple[str, str]:
    file_object = client.files.content(fileId)
    local_path = os.sep.join([FILE_STORE, fileId])
    with open(local_path, "wb") as file:
        file.write(file_object.content)
    file_str = base64.b64encode(file_object.content).decode()
    hyper_link = f'<a href="data:file/txt;base64,{file_str}" download="{fileName}">{fileName}</a>'
    LOGGER.info(f'saved file at local: {local_path}')
    return local_path, hyper_link


def process_message_with_citations(msg):
    """Extract content and annotations from the message and format citations as footnotes."""
    LOGGER.info(f'message_content={msg}')
    message_content = msg.content[0].text
    annotations = message_content.annotations if hasattr(message_content, 'annotations') else []
    citations = []
    if len(annotations) == 0:
        ret = re.findall(r'\n\n\[(.*?)\]\((.*?)\)', message_content.value)
        if len(ret) == 1:
            link_name, file_path = ret[0]
            fileId = file_path.split(os.sep)[-1]
            local_path, hyper_link = download_file(fileId)
            message_content.value = message_content.value.replace(f'[{link_name}]({file_path})', hyper_link)
        full_resp = message_content.value
    elif len(annotations) == 1:
        ret = re.findall(r'\n\n\[(.*?)\]\((.*?)\)', message_content.value)
        if len(ret) == 1:
            link_name, file_path = ret[0]
            file_name = file_path.split(os.sep)[-1]
            if anno_file_path := getattr(annotations[0], 'file_path', None):
                local_path, hyper_link = download_file(anno_file_path.file_id, file_name)
                message_content.value = message_content.value.replace(f'[{link_name}]({file_path})', hyper_link)
        full_resp = message_content.value
    else:
        # Iterate over the annotations and add footnotes
        for index, annotation in enumerate(annotations):
            # Replace the text with a footnote
            message_content.value = message_content.value.replace(annotation.text, f' [{index}]')
            # Gather citations based on annotation attributes
            if anno_file_citation := getattr(annotation, 'file_citation', None):
                cited_file = client.files.retrieve(anno_file_citation.file_id)
                citations.append(f'[{index}] {anno_file_citation.quote} 来自 {cited_file.filename}')
            elif anno_file_path := getattr(annotation, 'file_path', None):
                local_path, hyper_link = download_file(anno_file_path.file_id)
                citations.append(f'[{index}] {hyper_link}')
        full_resp = message_content.value + '\n\n' + '\n'.join(citations)
    return full_resp


with st.sidebar:
    st.image('assets/logo.png')
    st.subheader('', divider='blue')
    st.sidebar.header("设置")
    assistant_id = st.sidebar.text_input("输入助理ID")
    st.session_state.assistant_id = assistant_id

    uploaded_file = st.sidebar.file_uploader('请上传文件', type=["csv", "xls", "xlsx"],
                                             label_visibility='collapsed', key='file_uploader')
    if uploaded_file is not None:
        check_and_upload(uploaded_file)


if "thread_id" not in st.session_state:
    st.markdown(
        """
        # 欢迎使用数据分析小助理 #
        ---
        ### 使用步骤 ###
        1. 在设置栏中输入小助理ID，__并回车__
        2. 上传你要分析的csv或者excel文件
        3. 在对话框内输入你要查询的数据
        ### 查询示例 ###
        - ``找出`aum`最高的前10名用户姓名以及他们的理财师和最近联系时间(`last_contact_time`)，结果用表格展示``
        - ``最近10天有赎回的用户是哪些？他们的理财师在这段时间有跟他们联系过吗？``
        - ``找出近30天没有电话联系的用户姓名和对应的理财师，以及他们上次电话联系的时间(`last_call_time`)，用表格展示并提供下载链接``
    """
    )

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)

if prompt := st.chat_input("想分析什么数据?"):

    if "thread_id" not in st.session_state:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=prompt,
            file_ids=[f_id for f_id, f_name, f_md5 in st.session_state.file_id_list],
            metadata={f_id: f_name for f_id, f_name, f_md5 in st.session_state.file_id_list}
        )
        # Create a run with additional instructions
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=st.session_state.assistant_id,
        )

        # Poll for the run to complete and retrieve the assistant's messages
        while run.status != 'completed':
            message_placeholder.markdown("▌")
            time.sleep(2)
            message_placeholder.markdown(" ")
            run = client.beta.threads.runs.retrieve(
                thread_id=st.session_state.thread_id,
                run_id=run.id
            )

        # Retrieve messages added by the assistant
        messages = client.beta.threads.messages.list(
            thread_id=st.session_state.thread_id,
            limit=1,
            order='desc'
        )

        # Process and display assistant messages
        assistant_messages_for_run = [
            message for message in messages
            if message.run_id == run.id and message.role == "assistant"
        ]
        for message in assistant_messages_for_run:
            full_response = process_message_with_citations(message)
            message_placeholder.markdown(full_response, unsafe_allow_html=True)
            break
    st.session_state.messages.append({"role": "assistant", "content": full_response})
