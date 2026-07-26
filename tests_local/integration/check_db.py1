import chromadb

try:
    # 1. Connect to your local database folder
    client = chromadb.PersistentClient(path=".chroma")
    
    # 2. List all collections to verify what exists
    collections = client.list_collections()
    print("--- 📚 Collections Found ---")
    for col in collections:
        print(f"• Name: {col.name}")
        
    # 3. Get your OWASP collection and count the records
    collection = client.get_collection("owasp_knowledge")
    count = collection.count()
    print(f"\n--- 📊 Collection Stats ---")
    print(f"Collection Name: 'owasp_knowledge'")
    print(f"Total Documents Ingested: {count}")
    
    # 4. Peek at a sample document to make sure it reads correctly
    if count > 0:
        print(f"\n--- 🔍 Peek (Sample Document) ---")
        sample = collection.peek(limit=1)
        
        # Display sample details
        doc = sample['documents'][0]
        meta = sample['metadatas'][0]
        id_ = sample['ids'][0]
        
        print(f"ID: {id_}")
        print(f"Metadata: {meta}")
        print(f"Document Text snippet:\n\"{(doc[:200] + '...') if len(doc) > 200 else doc}\"")
    else:
        print("\n⚠️ The collection exists, but it contains 0 documents. Ingestion might have failed.")
        
except Exception as e:
    print(f"\n❌ Error accessing ChromaDB: {e}")