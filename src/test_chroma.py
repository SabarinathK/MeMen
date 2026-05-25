import chromadb

chroma_client = chromadb.PersistentClient(path="src/chroma_db")
collection = chroma_client.get_collection("mental_health_ltm")

# client = chromadb.PersistentClient(path="./chroma_db")  # your path
# collection = client.get_collection("user_memories")  # your collection name

# Get all entries (or a subset)
result = collection.get()

print(f"Total entries: ", result)
# print("Document IDs:", result["ids"])
# print("Metadata examples:")
# for md in result["metadatas"][:3]:
#     print(md)

# print("Document content examples:")
# for doc in result["documents"][:1]:
#     print(doc)
