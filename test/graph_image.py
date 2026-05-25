from src.agent.open_message import graph

app = graph.compile()


png_data = app.get_graph().draw_mermaid_png()

with open("graph.png", "wb") as f:
    f.write(png_data)

print("Saved graph.png")
