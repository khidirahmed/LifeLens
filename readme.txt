
python3 segment_receiver.py --host 0.0.0.0 --port 8788 --ws-port 8789
python relay_server.py --receiver-ws ws://100.85.243.115:8789 

scp /Users/shoujinhao/Documents/GitHub/LifeLens/stream_server/segment_receiver1.py \
  asus@100.85.243.115:~/Documents/stream_server/
scp /Users/shoujinhao/Documents/GitHub/LifeLens/analyze_video.py \
  asus@100.85.243.115:~/Documents/analyze_video.py


tailscale ssh asus@100.85.243.115 


python3 segment_receiver1.py --host 0.0.0.0 --port 8788 --ws-port 8789



uvicorn main:app --host 0.0.0.0 --port 8000 --reload


% rsync -avz -e "ssh -i temp.pem" \                               
  --exclude venv \
  --exclude __pycache__ \
  --exclude "*.pyc" \
  ./LifeLens/backend ec2-user@18.217.82.197:~
  