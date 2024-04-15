from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv
import os
from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin
import requests
import json

from chain import chain

app = Flask(__name__)

load_dotenv()

with open("../config.json") as config_file:
    config = json.load(config_file)

# CLOUD_ID = config["lee_cloud"]["Cloud_id"]
# API_KEY = config["lee_cloud"]["API_KEY"]
# SPOTIFY_CLIENT_ID = config["SPOTIFY"]["SPOTIFY_CLIENT_ID"]
# SPOTIFY_CLIENT_SECRET = config["SPOTIFY"]["SPOTIFY_CLIENT_SECRET"]
#
# index_name = "lee_test_1"
#
# # Elasticsearch client
# client = Elasticsearch(
#     cloud_id=CLOUD_ID,
#     api_key=API_KEY
# )

# public cloud
CLOUD_ID = config["public_cloud"]["Cloud_id"]
API_KEY = config["public_cloud"]["API_KEY"]
SPOTIFY_CLIENT_ID = config["SPOTIFY"]["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = config["SPOTIFY"]["SPOTIFY_CLIENT_SECRET"]

client = Elasticsearch(
    cloud_id=CLOUD_ID,
    api_key=API_KEY
)

index_name = "podcast"

# Get Token for Spotify API (valid for 1h)
response = requests.post("https://accounts.spotify.com/api/token",
                         data={"grant_type": "client_credentials", "client_id": SPOTIFY_CLIENT_ID,
                               "client_secret": SPOTIFY_CLIENT_SECRET})
if response.status_code == 404:
    print("Could not get spotify access token.")
    print(response.text)
    exit()

SPOTIFY_ACCESS_TOKEN = response.json()["access_token"]


# Read metadata.tsv file
# Returns map of episode_filename_prefix to metadata
def read_metadata():
    metadata = {}
    with open("../data/metadata.tsv", "r") as file:
        lines = file.readlines()
        for line in lines:
            episode_info = line.strip().split("\t")
            episode_filename_prefix = episode_info[-1]
            metadata[episode_filename_prefix] = {
                "show_name": episode_info[1],
                "show_description": episode_info[2],
                "publisher": episode_info[3],
                "language": episode_info[4],
                "rss_link": episode_info[5],
                "episode_uri": episode_info[6],
                "episode_name": episode_info[7],
                "episode_description": episode_info[8]
            }
    return metadata


metadata = read_metadata()


@app.route('/search')
@cross_origin(origin='*')
def get_incomes():
    search_query = request.args.get('q')
    print(search_query)
    invoke = chain.invoke({"input": search_query})
    print(invoke)
    search_result = client.search(index=index_name, query=invoke["query"], size=invoke["size"])
    hits = search_result["hits"]["hits"]

    # Map all hits from the same show and episode to the same dictionary
    episode_map = {}
    episode_ids = []
    for hit in hits:
        episode_id = hit["_source"]["episode_id"]
        episode_ids.append(episode_id)

        if episode_id not in episode_map:
            episode_map[episode_id] = {
                "show_id": hit["_source"]["show_id"],
                "episode_id": episode_id,
                "show_name": metadata[episode_id]["show_name"],
                "show_description": metadata[episode_id]["show_description"],
                "publisher": metadata[episode_id]["publisher"],
                "episode_name": metadata[episode_id]["episode_name"],
                "episode_description": metadata[episode_id]["episode_description"],
                "language": metadata[episode_id]["language"],
                "rss_link": metadata[episode_id]["rss_link"],
                "snippets": []
            }

        snippet = {
            "transcript_text": hit["_source"]["transcript_text"],
            "start_time": hit["_source"]["start_time"],
            "end_time": hit["_source"]["end_time"],
            "score": hit["_score"],
        }
        episode_map[episode_id]["snippets"].append(snippet)

    # Get Spotify episodes for each episode_id (get picture uri)
    episodes_response = requests.get("https://api.spotify.com/v1/episodes?market=SE&ids=" + ",".join(episode_ids),
                                     headers={"Authorization": "Bearer " + SPOTIFY_ACCESS_TOKEN})
    if episodes_response.status_code == 404:
        print("Could not get spotify episodes.")
        print(episodes_response.text)
        exit()

    episodes = episodes_response.json()["episodes"]
    for episode in episodes:
        if episode is None:
            continue

        episode_id = episode["id"]
        if episode_id in episode_map:
            episode_map[episode_id]["picture_uri"] = episode["images"][1]["url"]

    formatted_results = {"episodes": []}
    for episode_id, episode in episode_map.items():
        formatted_results["episodes"].append(episode)

    response = jsonify(formatted_results)
    # response.headers.add("Access-Control-Allow-Origin", "*")
    # response.headers.add("Access-Control-Allow-Headers", "Origin, X-Requested-With, Content-Type, Accept")
    return response


if __name__ == '__main__':
    app.run(debug=True)
