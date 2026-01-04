@echo off
setlocal
cd /d C:\Users\User\Projects\ea-stress-test-v2
C:\Python313\python.exe scripts\watch_batch.py --runs-dir "C:\Users\User\Projects\ea-stress-test-v2\runs\batch" --stale-minutes 20 --desktop-alert --task-name EAStressBatchWatchdog
endlocal
