import os

from langchain_community.document_loaders import UnstructuredMarkdownLoader

from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_community.embeddings import SentenceTransformerEmbeddings

from langchain_community.vectorstores import Chroma

from langchain.chains import RetrievalQA

from langchain_openai import ChatOpenAI



# 2. 加载并分割Markdown文件

loader = UnstructuredMarkdownLoader("your_faq.md")

documents = loader.load()



text_splitter = RecursiveCharacterTextSplitter(

    chunk_size=500,

    chunk_overlap=50,

    separators=["\n## ", "\n### ", "\n\n", "\n", " "] # 按Markdown标题分割

)

chunks = text_splitter.split_documents(documents)



# 3. 创建本地向量库

embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")

vectorstore = Chroma.from_documents(

    documents=chunks,

    embedding=embeddings,

    persist_directory="./chroma_db" # 数据持久化到本地

)



# 4. 创建检索链并提问

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0) # 替换为你的API Key

qa_chain = RetrievalQA.from_chain_type(

    llm=llm,

    retriever=vectorstore.as_retriever(),

    return_source_documents=True

)



# 5. 开始问答

question = "你的问题是什么？"

result = qa_chain.invoke({"query": question})

print("答案:", result["result"])

print("参考来源:", result["source_documents"])