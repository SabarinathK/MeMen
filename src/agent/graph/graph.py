from MeMen.src.agent.state import ChatState
from MeMen.src.agent.node.memory_node import memory_node
from MeMen.src.agent.node.todo_node import todo_node
from langgraph.graph import StateGraph, START, END
from MeMen.src.agent.node.emotion_node import emotion_node
from MeMen.src.agent.node.sync_barrier import sync_barrier
from MeMen.src.agent.node.response_node import response_node
from MeMen.src.agent.node.followup_node import followup_node
from MeMen.src.agent.node.mem0_save_node import mem0_save_node

builder = StateGraph(ChatState)

builder.add_node("memory_node", memory_node)
builder.add_node("todo_node", todo_node)
builder.add_node("emotion_node", emotion_node)
builder.add_node("sync_barrier", sync_barrier)
builder.add_node("response_node", response_node)
builder.add_node("followup_node", followup_node)
builder.add_node("mem0_save_node", mem0_save_node)

# Fan-out from START (parallel)
builder.add_edge(START, "memory_node")
builder.add_edge(START, "todo_node")
builder.add_edge(START, "emotion_node")

# Fan-in to barrier (LangGraph waits for all three before proceeding)
builder.add_edge("memory_node", "sync_barrier")
builder.add_edge("todo_node", "sync_barrier")
builder.add_edge("emotion_node", "sync_barrier")

# Sequential from here — reply is fully written before fan-out
builder.add_edge("sync_barrier", "response_node")
builder.add_edge("response_node", "followup_node")
builder.add_edge("response_node", "mem0_save_node")
builder.add_edge("followup_node", END)
builder.add_edge("mem0_save_node", END)

graph = builder.compile()
