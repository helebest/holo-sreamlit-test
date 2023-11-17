import os
import time
import streamlit as st
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI

load_dotenv(find_dotenv())
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Set up the Streamlit page with a title and icon
st.set_page_config(page_title="你的AI助理", layout="wide", page_icon=":speech_balloon:")

default_title = '新的对话'

# Set a default model
if "openai_model" not in st.session_state:
    st.session_state.openai_model = os.getenv('MODEL_NAME')

if 'index' not in st.session_state:
    st.session_state.index = 0

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []


def process_message_with_citations(msg):
    """Extract content and annotations from the message and format citations as footnotes."""
    message_content = msg.content[0].text
    annotations = message_content.annotations if hasattr(message_content, 'annotations') else []
    citations = []

    # Iterate over the annotations and add footnotes
    for index, annotation in enumerate(annotations):
        # Replace the text with a footnote
        message_content.value = message_content.value.replace(annotation.text, f' [{index + 1}]')

        # Gather citations based on annotation attributes
        if file_citation := getattr(annotation, 'file_citation', None):
            # Retrieve the cited file details (dummy response here since we can't call OpenAI)
            cited_file = {'filename': 'cited_document.pdf'}  # This should be replaced with actual file retrieval
            citations.append(f'[{index + 1}] {file_citation.quote} from {cited_file["filename"]}')
        elif file_path := getattr(annotation, 'file_path', None):
            # Placeholder for file download citation
            cited_file = {'filename': 'downloaded_document.pdf'}  # This should be replaced with actual file retrieval
            citations.append(
                f'[{index + 1}] Click [here](#) to download {cited_file["filename"]}')  # The download link should be replaced with the actual download path
    # Add footnotes to the end of the message content
    full_resp = message_content.value + '\n\n' + '\n'.join(citations)
    return full_resp


with st.sidebar:
    st.sidebar.header("设置")
    assistant_id = st.sidebar.text_input("输入助理ID")
    st.session_state.assistant_id = assistant_id


# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("说点什么吧?"):

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
            content=prompt
        )
        # Create a run with additional instructions
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=st.session_state.assistant_id,
        )

        # Poll for the run to complete and retrieve the assistant's messages
        while run.status != 'completed':
            time.sleep(2)
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
            message_placeholder.markdown(full_response)
            break
    st.session_state.messages.append({"role": "assistant", "content": full_response})
