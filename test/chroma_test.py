import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection("mental_health_ltm")

data = collection.get(where={"user_id": "668e3db5-9f2b-4320-9aeb-eab95f0a30ff"})

results = []
for i in range(len(data["ids"])):
    results.append(
        {
            "id": data["ids"][i],
            "text_lemmatized": data["metadatas"][i].get("text_lemmatized", ""),
            "metadata": data["metadatas"][i],
        }
    )

latest_5 = sorted(
    results,
    key=lambda x: x["metadata"].get("created_at", ""),
    reverse=True,
)[:5]

res = [item["text_lemmatized"] for item in latest_5 if item["text_lemmatized"]]
print(res)
