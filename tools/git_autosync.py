"""
Git 자동 동기화 데몬
- Calib 폴더의 파일 변경(생성/수정/삭제)을 감지해 자동으로 commit + push
- 변경이 연속으로 일어날 때 불필요한 커밋이 쌓이지 않도록 DEBOUNCE_SEC 초 대기 후 처리

실행 방법:
  python tools/git_autosync.py

의존 패키지:
  pip install watchdog
"""
import time
import subprocess
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_DIR     = r"C:\Users\tilti\OneDrive\Calib"
DEBOUNCE_SEC = 5      # 마지막 변경 후 이 시간만큼 기다렸다가 커밋
BRANCH       = "main"

# 감시에서 제외할 경로/패턴
IGNORE_DIRS  = {".git", ".claude", ".idea", "__pycache__", "lwir", "visible"}
IGNORE_EXTS  = {".npz", ".npy", ".pyc"}


def run(cmd, cwd=REPO_DIR):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0 and result.stderr:
        print(f"  [git] {result.stderr.strip()}")
    return result


def has_changes():
    r = run(["git", "status", "--porcelain"])
    return bool(r.stdout.strip())


def commit_and_push():
    if not has_changes():
        return

    run(["git", "add",
         "*.py", "tools/*.py",         # Python 파일
         "*.md", "*.txt", "*.json",    # 문서/설정
         "--ignore-errors"])

    # 변경 요약을 커밋 메시지에 포함
    status = run(["git", "status", "--short"]).stdout.strip()
    lines  = status.splitlines()
    if len(lines) == 1:
        msg = f"auto: {lines[0].strip()}"
    else:
        msg = f"auto: {len(lines)} files changed"

    run(["git", "commit", "-m", msg])
    result = run(["git", "push", "origin", BRANCH])

    if result.returncode == 0:
        print(f"[sync] pushed — {msg}")
    else:
        print(f"[sync] push 실패: {result.stderr.strip()}")


class ChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self._last_change = 0

    def _should_ignore(self, path):
        p = Path(path)
        # 제외 디렉토리
        for part in p.parts:
            if part in IGNORE_DIRS:
                return True
        # 제외 확장자
        if p.suffix.lower() in IGNORE_EXTS:
            return True
        return False

    def _on_any(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        self._last_change = time.time()

    on_created  = _on_any
    on_modified = _on_any
    on_deleted  = _on_any
    on_moved    = _on_any


def main():
    print(f"[autosync] 감시 시작: {REPO_DIR}")
    print(f"[autosync] 변경 감지 후 {DEBOUNCE_SEC}초 대기 → commit + push")
    print("[autosync] 종료: Ctrl+C\n")

    handler  = ChangeHandler()
    observer = Observer()
    observer.schedule(handler, REPO_DIR, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
            elapsed = time.time() - handler._last_change
            if handler._last_change > 0 and elapsed >= DEBOUNCE_SEC:
                handler._last_change = 0  # 리셋 (중복 방지)
                commit_and_push()
    except KeyboardInterrupt:
        print("\n[autosync] 종료")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
