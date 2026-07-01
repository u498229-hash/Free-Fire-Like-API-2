from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
from google.protobuf.message import DecodeError
import base64
import logging

app = Flask(__name__)

# ========== LOGGING SETUP ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_tokens():
    try:
        with open("tokens.json", "r") as f:
            tokens = json.load(f)
        logger.info(f"✅ Loaded {len(tokens)} tokens")
        return tokens
    except Exception as e:
        logger.error(f"❌ Error loading tokens: {e}")
        return None

def encrypt_message(plaintext):
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        return binascii.hexlify(encrypted_message).decode('utf-8')
    except Exception as e:
        logger.error(f"❌ Encryption error: {e}")
        return None

def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        return message.SerializeToString()
    except Exception as e:
        logger.error(f"❌ Protobuf error: {e}")
        return None

async def send_request(encrypted_uid, token, url, request_id):
    """Send like request with request ID for tracking"""
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2022.3.47f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB54"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=10) as response:
                status = response.status
                logger.info(f"📡 Request {request_id}: Status {status}")
                return {"request_id": request_id, "status": status, "token": token[:20] + "..."}
    except Exception as e:
        logger.error(f"❌ Request {request_id} error: {e}")
        return {"request_id": request_id, "status": 500, "error": str(e)}

async def send_multiple_requests(uid, server_name, url):
    try:
        region = server_name
        protobuf_message = create_protobuf_message(uid, region)
        if protobuf_message is None:
            logger.error("❌ Failed to create protobuf message")
            return None, 0, 0
            
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            logger.error("❌ Encryption failed")
            return None, 0, 0
            
        tasks = []
        tokens = load_tokens()
        if tokens is None or not tokens:
            logger.error("❌ No tokens found")
            return None, 0, 0
        
        # ✅ 20 likes per token
        total_requests = len(tokens) * 20
        logger.info(f"📊 Sending {total_requests} likes with {len(tokens)} tokens")
        
        request_id = 0
        for i in range(total_requests):
            token = tokens[i % len(tokens)]["token"]
            tasks.append(send_request(encrypted_uid, token, url, request_id))
            request_id += 1
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # ✅ Debug: Count success/failed
        success = 0
        failed = 0
        for r in results:
            if isinstance(r, dict) and r.get("status") == 200:
                success += 1
            else:
                failed += 1
        
        logger.info(f"📊 Total Requests: {len(results)}")
        logger.info(f"📊 Successful: {success}")
        logger.info(f"📊 Failed: {failed}")
        
        # Log first 5 results for debugging
        for i, r in enumerate(results[:5]):
            logger.info(f"📊 Result {i}: {r}")
        
        return results, success, failed
    except Exception as e:
        logger.error(f"❌ Error in send_multiple_requests: {e}")
        return None, 0, 0

def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        logger.error(f"❌ Error creating uid protobuf: {e}")
        return None

def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    encrypted_uid = encrypt_message(protobuf_data)
    return encrypted_uid

def make_request(encrypt, server_name, token):
    try:
        if server_name == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
            
        edata = bytes.fromhex(encrypt)
        headers = {
            'User-Agent': "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2022.3.47f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB54"
        }
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
        hex_data = response.content.hex()
        binary = bytes.fromhex(hex_data)
        decode = decode_protobuf(binary)
        if decode is None:
            logger.error("❌ Protobuf decoding returned None")
        return decode
    except Exception as e:
        logger.error(f"❌ Error in make_request: {e}")
        return None

def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except DecodeError as e:
        logger.error(f"❌ Protobuf decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected decode error: {e}")
        return None

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "credit": "UZAIR MODS",
        "message": "Welcome to the Free Fire Like API",
        "status": "API is running",
        "endpoints": "/like?uid=<uid> or /like?uid=<uid>&server_name=<server_name>",
        "example": "/like?uid=123456789 or /like?uid=123456789&server_name=PK"
})

@app.route('/like', methods=['GET'])
def handle_requests():
    uid = request.args.get("uid")
    if not uid:
        return jsonify({"error": "UID is required"}), 400

    try:
        tokens = load_tokens()
        if tokens is None or not tokens:
            return jsonify({"error": "Failed to load tokens."}), 500
            
        token = tokens[0]['token']
        
        # Extract server_name (lock_region) from token if not provided
        server_name = request.args.get("server_name", "").upper()
        if not server_name:
            try:
                payload = token.split('.')[1]
                payload += '=' * (-len(payload) % 4)
                decoded_payload = base64.urlsafe_b64decode(payload).decode('utf-8')
                parsed_payload = json.loads(decoded_payload)
                server_name = parsed_payload.get('lock_region', '').upper()
                logger.info(f"📍 Detected region from token: {server_name}")
            except Exception as e:
                logger.error(f"❌ Error decoding token: {e}")
        
        if not server_name:
            return jsonify({"error": "server_name could not be determined from token or input"}), 400
        
        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            return jsonify({"error": "Encryption of UID failed."}), 500

        # Get before likes count
        before = make_request(encrypted_uid, server_name, token)
        if before is None:
            return jsonify({"error": "Failed to retrieve player info. No valid token found! Please update tokens.json"}), 500
        
        data_before = json.loads(MessageToJson(before))
        before_like = int(data_before.get('AccountInfo', {}).get('Likes', 0) or 0)
        logger.info(f"📊 Likes before: {before_like}")

        # Determine URL based on server
        if server_name == "IND":
            url = "https://client.ind.freefiremobile.com/LikeProfile"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/LikeProfile"
        else:
            url = "https://clientbp.ggpolarbear.com/LikeProfile"

        # Send like requests with debug info
        requests_sent, success, failed = asyncio.run(send_multiple_requests(uid, server_name, url))
        logger.info(f"📊 Requests sent: {len(requests_sent) if requests_sent else 0}")
        logger.info(f"📊 Successful: {success}")
        logger.info(f"📊 Failed: {failed}")

        # Get after likes count
        after = make_request(encrypted_uid, server_name, token)
        if after is None:
            return jsonify({"error": "Failed to retrieve player info after likes."}), 500
        
        data_after = json.loads(MessageToJson(after))
        account_info = data_after.get('AccountInfo', {})
        after_like = int(account_info.get('Likes', 0) or 0)
        player_uid = int(account_info.get('UID', 0) or 0)
        player_name = str(account_info.get('PlayerNickname', ''))
        
        like_given = after_like - before_like
        status = 1 if like_given > 0 else 2
        
        logger.info(f"📊 Likes after: {after_like} | Given: {like_given} | Status: {status}")

        # ✅ Response with debug info
        return jsonify({
            "credit": "https://t.me/paglu_dev",
            "LikesGivenByAPI": like_given,
            "LikesafterCommand": after_like,
            "LikesbeforeCommand": before_like,
            "PlayerNickname": player_name,
            "Region": server_name,
            "UID": player_uid,
            "TotalRequests": len(requests_sent) if requests_sent else 0,
            "SuccessfulRequests": success,
            "FailedRequests": failed,
            "status": status
        })
    except Exception as e:
        logger.error(f"❌ Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
