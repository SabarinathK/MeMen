# app.py

import asyncio
from uuid import UUID, uuid4

import streamlit as st

from sqlmodel import select

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)

from MeMen.src.database import get_session

from MeMen.src.models import (
    User,
    Conversation,
    Message,
    TodoItem,
)

# IMPORT FROM YOUR EXISTING GRAPH FILE
from MeMen.src.agent.open_message import (
    load_long_term_memories,
    load_pending_todos,
    mark_todos_used,
    generate_opening_message,
)
from MeMen.src.agent.graph.graph import graph

st.set_page_config(
    page_title="MeMen",
    layout="wide",
)


if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None


if not st.session_state.user_id:

    st.title("MeMen")

    username = st.text_input("Username")

    password = st.text_input(
        "Password",
        type="password",
    )

    if st.button("Login"):

        with get_session() as session:

            user = session.exec(select(User).where(User.username == username)).first()

            if not user:

                st.error("User not found")

                st.stop()

            st.session_state.user_id = str(user.id)

            st.rerun()

    st.stop()

with st.sidebar:

    st.title("MeMen")

    # NEW CHAT
    if st.button("+ New Chat"):

        conversation_id = uuid4()

        with get_session() as session:

            conversation = Conversation(
                id=conversation_id,
                user_id=UUID(st.session_state.user_id),
                title="New conversation",
            )

            session.add(conversation)

            session.commit()

        # OPENING PIPELINE
        memories = asyncio.run(load_long_term_memories(st.session_state.user_id))
        print("\n[long-term memories]", memories, "\n")

        todos = load_pending_todos(UUID(st.session_state.user_id))
        print("\n[pending todos]", todos, "\n")

        opening = asyncio.run(
            generate_opening_message(
                memories,
                todos,
            )
        )

        mark_todos_used(UUID(st.session_state.user_id))

        with get_session() as session:

            opening_message = Message(
                conversation_id=conversation_id,
                user_id=UUID(st.session_state.user_id),
                role="assistant",
                content_encrypted=opening,
            )

            session.add(opening_message)

            session.commit()

        st.session_state.conversation_id = str(conversation_id)

        st.rerun()

    st.divider()

    st.subheader("Conversations")

    with get_session() as session:

        conversations = session.exec(
            select(Conversation)
            .where(Conversation.user_id == UUID(st.session_state.user_id))
            .order_by(Conversation.created_at.desc())
        ).all()

    for convo in conversations:

        if st.button(
            convo.title,
            key=str(convo.id),
            use_container_width=True,
        ):

            st.session_state.conversation_id = str(convo.id)

            st.rerun()


left, right = st.columns([3, 1])


with left:

    st.title("MeMen")

    if not st.session_state.conversation_id:

        st.info("Create a new conversation.")

        st.stop()

    # LOAD MESSAGES
    with get_session() as session:

        messages = session.exec(
            select(Message)
            .where(Message.conversation_id == UUID(st.session_state.conversation_id))
            .order_by(Message.created_at.asc())
        ).all()

    # DISPLAY
    for msg in messages:

        with st.chat_message(msg.role):

            st.write(msg.content_encrypted)

    # INPUT
    user_input = st.chat_input("Talk to MeMen...")

    if user_input:

        # USER MESSAGE UI
        with st.chat_message("user"):

            st.write(user_input)

        # BUILD HISTORY
        history = []

        for msg in messages:

            if msg.role == "user":

                history.append(HumanMessage(content=msg.content_encrypted))

            else:

                history.append(AIMessage(content=msg.content_encrypted))

        # GRAPH STATE
        state = {
            "user_id": st.session_state.user_id,
            "conversation_id": st.session_state.conversation_id,
            "user_input": user_input,
            "history": history,
            "relevant_memories": [],
            "emotion": "neutral",
            "todo_status": "NONE",
            "active_todo": "",
            "reply": "",
        }

        # RUN GRAPH
        result = asyncio.run(graph.ainvoke(state))

        reply = result["reply"]

        # ASSISTANT UI
        with st.chat_message("assistant"):

            st.write(reply)

        # SAVE MESSAGES
        with get_session() as session:

            session.add(
                Message(
                    conversation_id=UUID(st.session_state.conversation_id),
                    user_id=UUID(st.session_state.user_id),
                    role="user",
                    content_encrypted=user_input,
                )
            )

            session.add(
                Message(
                    conversation_id=UUID(st.session_state.conversation_id),
                    user_id=UUID(st.session_state.user_id),
                    role="assistant",
                    content_encrypted=reply,
                )
            )

            session.commit()

        st.rerun()


with right:

    st.title("Todos")

    with get_session() as session:

        todos = session.exec(
            select(TodoItem)
            .where(TodoItem.user_id == UUID(st.session_state.user_id))
            .order_by(TodoItem.created_at.desc())
        ).all()

    pending = [t for t in todos if t.status == "pending"]

    done = [t for t in todos if t.status == "done"]

    dismissed = [t for t in todos if t.status == "dismissed"]

    st.subheader("Pending")

    for todo in pending:

        st.markdown(f"""
- {todo.text}
""")

    st.divider()

    st.subheader("Done")

    for todo in done:

        st.markdown(f"""
✅ {todo.text}
""")

    st.divider()

    st.subheader("Dismissed")

    for todo in dismissed:

        st.markdown(f"""
❌ {todo.text}
""")
