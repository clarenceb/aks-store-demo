# Credits: https://github.com/paolosalvatori/aks-kaito-terraform
# Install:
#   sudo apt install python3-pip
#   python -m pip install --upgrade setuptools
#   python -m pip install -r requirements.txt
# Run:
#   python -m chainlit run app.py -w

# Import packages
import os
import sys
import requests
import json
import logging
import chainlit as cl
from dotenv import load_dotenv
from dotenv import dotenv_values

# Load environment variables from .env file
if os.path.exists(".env"):
    load_dotenv(override=True)
    config = dotenv_values(".env")

# Read environment variables
temperature = float(os.environ.get("TEMPERATURE", 0.9))
top_p = float(os.environ.get("TOP_P", 1))
top_k = float(os.environ.get("TOP_K", 10))
max_length = int(os.environ.get("MAX_LENGTH", 4096))
max_retries = int(os.getenv("MAX_RETRIES", 5))
timeout = int(os.getenv("TIMEOUT", 30))
debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
aiEndpoint = os.getenv("AI_ENDPOINT", "")

# Configure a logger
logging.basicConfig(
    stream=sys.stdout,
    format="[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

@cl.on_chat_start
async def start_chat():
    await cl.Avatar(
        name="Chatbot",
        url="https://cdn-icons-png.flaticon.com/512/8649/8649595.png",
    ).send()
    await cl.Avatar(
        name="Error",
        url="https://cdn-icons-png.flaticon.com/512/8649/8649595.png",
    ).send()
    await cl.Avatar(
        name="You",
        url="https://media.architecturaldigest.com/photos/5f241de2c850b2a36b415024/master/w_1600%2Cc_limit/Luke-logo.png",
    ).send()

@cl.on_message
async def on_message(message: cl.Message):

    # Create the Chainlit response message
    msg = cl.Message(content="")

    payload = {
        "prompt": f"{message.content} answer:",
        "return_full_text": False,
        "clean_up_tokenization_spaces": False, 
        "prefix": None,
        "handle_long_generation": None,
        "generate_kwargs": {
            "max_length": max_length,
            "min_length": 0,
            "do_sample": True,
            "early_stopping": False,
            "num_beams":1,
            "num_beam_groups":1,
            "diversity_penalty":0.0,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
            "typical_p": 1,
            "repetition_penalty": 1,
            "length_penalty": 1,
            "no_repeat_ngram_size":0,
            "encoder_no_repeat_ngram_size":0,
            "bad_words_ids": None,
            "num_return_sequences":1,
            "output_scores": False,
            "return_dict_in_generate": False,
            "forced_bos_token_id": None,
            "forced_eos_token_id": None,
            "remove_invalid_values": True
        }
    }

    # payload = {
    #     "prompt": f"{message.content} answer:",
    #     "return_full_text": False
    # }

    headers = {"Content-Type": "application/json", "accept": "application/json"}
    response = requests.request(
        method="POST", 
        url=aiEndpoint, 
        headers=headers, 
        json=payload
    )

    # convert response.text to json
    result = json.loads(response.text)
    result = result["Result"]

    # remove all double quotes
    if '"' in result:
        result = result.replace('"', "")

    msg.content = result

    await msg.send()
