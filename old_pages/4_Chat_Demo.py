import streamlit as st
import os
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())


st.title("你的ChatGPT助理")

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Set a default model
if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = os.getenv('MODEL_NAME')

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("说点什么吧?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = client.chat.completions.create(
            model=st.session_state["openai_model"],
            messages=[
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ],
            #stream=True,
        )
        response = full_response.choices[0].message.content
        message_placeholder.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
