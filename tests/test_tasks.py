import sys
sys.path.append(".")

from tool2 import load_tool
from models import Task

user = "65284b18f8bbb9bff13ebe65"


def test_trainer_task():
    args = {
        "name": "Verdelis",
        "lora_training_urls": [
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/kyuuefmnf56cnot8mqug.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/u215yeg4zrka2li0lcb7.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/pqu4j4n4ytptmlbcrb39.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/bvp3jz5onrswtxu7uf56.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/ncvw1ct6mx77vixi0stt.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/jljlboduzcneveg4kxpo.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502852/user_uploads/zmpzbyyycxazkr4blqhy.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502852/user_uploads/fvgtfar6ivjlnxx86kp4.jpg",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502856/user_uploads/ovpw8eub0kwjshqiwfcy.jpg"
        ],
        "sd_model_version": "sdxl",
        "concept_mode": "face",
        "max_train_steps": 500
    }

    task = Task(
        workflow="lora_trainer",
        args=args,
        user=user
    )

    trainer = load_tool("tools/lora_trainer")
    result = trainer.submit_and_run(task)
    
    print(result)



def test_creation_task():
    args = {
        "prompt": "Verdelis as a spectator at a movie theater, next to her friends and other viewers and visitors",
        "lora": "66c15ab898878d3b53bc1870",
        "lora_strength": 0.25,
        "width": 1440
    }

    task = Task(
        workflow="txt2img",
        args=args,
        user=user
    )

    txt2img = load_tool("../workflows/environments/txt2img/workflows/txt2img")
    result = txt2img.submit_and_run(task)
    
    print(result)




def test_upscaler_task():
    args = {
        "image": "http://4.bp.blogspot.com/-gx1tuHXeaSA/Tc2ut4VVvJI/AAAAAAAAAVs/6ND6FL1avvY/s1600/ben-grasso.jpg"
    }

    task = Task(
        workflow="clarity_upscaler",
        args=args,
        user=user
    )

    upscaler = load_tool("tools/clarity_upscaler")
    result = upscaler.submit_and_run(task)
    
    print(result)


test_trainer_task()
# test_creation_task()
# test_upscaler_task()