import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os

class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            filepath = event.src_path
            print(f"新しいファイルが追加されました: {filepath}")
            # ここでファイルタイプ判定 & Django API に送信
            process_file(filepath)

def process_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        print("PDFファイルを解析します")
        # PDF抽出処理
    elif ext == ".txt":
        print("TXTファイルを解析します")
    elif ext == ".md":
        print("Markdownファイルを解析します")
    else:
        print("対応していないファイル形式です")

if __name__ == "__main__":
    path = "study_materials"
    event_handler = FileHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

