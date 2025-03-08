conda create -n MoG python=3.8.5
conda activate MoG
pip install torch==2.1.0+cu121 torchvision==0.16.0+cu121 --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
