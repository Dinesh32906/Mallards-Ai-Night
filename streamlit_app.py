import streamlit as st
import pandas as pd
from snowflake.connector import connect
# from config import get_snowflake_connection
from snowflake.connector import connect


def get_snowflake_connection():
    try:
        conn = connect(
            user=st.secrets.db_credentials.SNOWFLAKE_USER,
            password=st.secrets.db_credentials.SNOWFLAKE_PASSWORD,
            account=st.secrets.db_credentials.SNOWFLAKE_ACCOUNT,
            role=st.secrets.db_credentials.SNOWFLAKE_ROLE,
            warehouse=st.secrets.db_credentials.SNOWFLAKE_WAREHOUSE,
            database=st.secrets.db_credentials.SNOWFLAKE_DATABASE,
            schema=st.secrets.db_credentials.SNOWFLAKE_SCHEMA
        )
        return conn
    except Exception as e:
        raise Exception(f"Error connecting to Snowflake: {e}")


# Default values
num_chunks = 1
slide_window = 7
model_name = 'llama3.1-405b'  # Fixed model

def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "use_chat_history" not in st.session_state:
        st.session_state.use_chat_history = True

def init_messages():
    if "clear_conversation" in st.session_state and st.session_state.clear_conversation:
        st.session_state.messages = []

def get_similar_chunks(question, session):
    cmd = """
        WITH results AS (
            SELECT RELATIVE_PATH,
                   VECTOR_COSINE_SIMILARITY(docs_chunks_table.chunk_vec,
                                            SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', %s)) AS similarity,
                   chunk
            FROM docs_chunks_table
            ORDER BY similarity DESC
            LIMIT %s)
        SELECT chunk, relative_path FROM results
    """
    cur = session.cursor()
    cur.execute(cmd, (question, num_chunks))
    rows = cur.fetchall()
    cur.close()
    
    df_chunks = pd.DataFrame(rows, columns=['chunk', 'relative_path'])
    
    df_chunks_length = len(df_chunks) - 1

    similar_chunks = ""
    for i in range(df_chunks_length):
        similar_chunks += df_chunks.iloc[i]['chunk']
    similar_chunks = similar_chunks.replace("'", "")
    
    return df_chunks.iloc[0]['chunk']

def get_chat_history():
    chat_history = []
    start_index = max(0, len(st.session_state.messages) - slide_window)
    for i in range(start_index, len(st.session_state.messages)):
        chat_history.append(st.session_state.messages[i]["content"])
    return chat_history

def summarize_question_with_history(chat_history, question, session):
    prompt = f"""
        Based on the chat history below and the question, generate a query that extends the question
        with the chat history provided. The query should be in natural language. 
        Answer with only the query. Do not add any explanation.
        
        <chat_history>
        {chat_history}
        </chat_history>
        <question>
        {question}
        </question>
        """
    
    cmd = """
        SELECT snowflake.cortex.complete(%s, %s) AS response
    """
    cur = session.cursor()
    cur.execute(cmd, (model_name, prompt))
    rows = cur.fetchall()
    cur.close()
    
    summary = rows[0][0]
    summary = summary.replace("'", "")
    return summary

def create_prompt(myquestion, session):
    if st.session_state.use_chat_history:
        chat_history = get_chat_history()
        if chat_history:
            question_summary = summarize_question_with_history(chat_history, myquestion, session)
            prompt_context = get_similar_chunks(question_summary, session)
        else:
            prompt_context = get_similar_chunks(myquestion, session)
    else:
        prompt_context = get_similar_chunks(myquestion, session)
        chat_history = ""
    st.write(prompt_context)
    prompt = f"""
        You are an expert chat assistant that extracts information from the CONTEXT provided
        between <context> and </context> tags.
        You offer a chat experience considering the information included in the CHAT HISTORY
        provided between <chat_history> and </chat_history> tags.
        When answering the question contained between <question> and </question> tags
        be concise and do not hallucinate. 
        If you don’t have the information just say so. 

        If you get relevant information od product from any combo say so.
        
        # If you do not know the price, do not give the price.
        
        Do not mention the CONTEXT used in your answer.
        Do not mention the CHAT HISTORY used in your answer.
        
        <chat_history>
        {chat_history}
        </chat_history>
        <context>
        {prompt_context}
        </context>
        <question>
        {myquestion}
        </question>
        Answer:
        """
    return prompt

def complete(myquestion, session):
    prompt = create_prompt(myquestion, session)
    cmd = """
        SELECT snowflake.cortex.complete(%s, %s) AS response
    """
    cur = session.cursor()
    cur.execute(cmd, (model_name, prompt))
    rows = cur.fetchall()
    cur.close()
    
    return rows[0][0]

def main():
    init_session_state()

    # Adding custom HTML and CSS
    # Adding custom HTML and CSS
    custom_html = """
    <style>
    #made-with-love {
    position: fixed;
    bottom: 20px;  /* Adjusted height */
    left: 10px;    /* Shifted to the left */
    font-size: 12px;
    color: #333;
    background-color: #f9f9f9;
    padding: 5px 10px;
    border-radius: 5px;
    z-index: 1000;
    }
    </style>
    <div id="made-with-love">
    Made with ❤️ by Pandata Group 🐼
    </div>
    """

# Render the custom HTML
    st.markdown(custom_html, unsafe_allow_html=True)
    
    # Display the logo with a smaller width
    st.image("logo.png", width=150)  # Adjust the width as needed

    st.title("💬 Mallards AI Assistant")
    st.markdown("<h3 style='font-size:14px;'>Welcome to the Mallards AI Assistant! Please ask me questions about the game, stadium, food available, or anything you might find on a Mallards F.A.Q. page!</h3>", unsafe_allow_html=True)
    st.markdown("<h3 style='font-size:14px;'>Please remember I am an AI agent please reach out to concessions or Restaurant for most accurate answer on the menu.</h3>", unsafe_allow_html=True)
    
    conn = get_snowflake_connection()
    
    if conn:
        session = conn
        init_messages()
        
        
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if question := st.chat_input("What do you want to know about Mallards?"):
            st.session_state.messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                question = question.replace("'", "")
                with st.spinner("Mallards AI thinking..."):
                    response = complete(question, session)
                    res_text = response
                    res_text = res_text.replace("'", "")
                    message_placeholder.markdown(res_text)
            st.session_state.messages.append({"role": "assistant", "content": res_text})
        session.close()
    else:
        st.error("Failed to connect to Snowflake.")

if __name__ == "__main__":
    main()
