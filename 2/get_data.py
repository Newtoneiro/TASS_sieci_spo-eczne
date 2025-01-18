from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Dict, Optional
from collections import Counter
import musicbrainzngs
import json
import time
import os
import streamlit as st


SAVE_FOLDER = os.path.join(os.path.dirname(__file__), "saved")


# Spotify API setup
spotify = Spotify(
    client_credentials_manager=SpotifyClientCredentials(
        client_id="963c976b97b14b1a9595d510feba38f4",
        client_secret="f89bc5064dd5487396181a312bbf2075",
    )
)
# Set up the MusicBrainz API client
musicbrainzngs.set_useragent("MusicDataScraper", "1.0", "example@example.com")


@st.cache_data(persist="disk")
def get_artist_info(artist_name: str) -> Dict:
    """
    Fetch the MusicBrainz ID and origin country of an artist by their name.

    Args:
        artist_name (str): The name of the artist.

    Returns:
        dict: A dictionary containing the artist ID, name, origin country, and additional metadata.
    """
    print(f"Fetching artist information for: {artist_name}")
    try:
        result = musicbrainzngs.search_artists(artist=artist_name, limit=1, strict=True)
        if result["artist-list"]:
            artist = result["artist-list"][0]
            artist_id = artist["id"]

            artist_details = musicbrainzngs.get_artist_by_id(
                artist_id, includes=["area-rels"]
            )
            origin_country = artist_details["artist"].get("area", {}).get("name", None)

            return {
                "artist_id": artist_id,
                "artist_name": artist["name"],
                "origin_country": origin_country,
                "life_span": artist.get("life-span", {}),
                "disambiguation": artist.get("disambiguation", {}),
                "tags": artist.get("tag-list", []),
            }
        else:
            return {
                "artist_id": "unknown",
                "artist_name": artist_name,
                "origin_country": "unknown",
                "life_span": {},
                "disambiguation": {},
                "tags": [],
            }
    except musicbrainzngs.ResponseError as e:
        raise Exception(f"Error fetching artist information for {artist_name}: {e}")


def filter_coauthor(coauthor_info: dict, filters: List) -> bool:
    """
    Filter a coauthor based on a given filter name and value.

    Args:
        coauthor_info (dict): The coauthor dictionary to filter.
        filters (list): The pairs of value, filter function

    Returns:
        bool: True if the coauthor matches the filter, False otherwise.
    """

    if coauthor_info is None:
        return False

    for filter_val, filter_func in filters:
        if filter_val in [None, ""]:
            continue

        if not filter_func(coauthor_info, filter_val):
            return False

    return True


@st.cache_data(persist="disk")
def get_songs_from_artist(artist_id: str) -> List[Dict]:
    """
    Fetch all songs by an artist along with release dates and ISRC codes.

    Args:
        artist_id (str): The MusicBrainz ID of the artist.

    Returns:
        list: A list of dictionaries containing song details.
    """
    print(f"Fetching songs for artist ID: {artist_id}")
    try:
        batch_size = 100
        offset = 0
        songs = {}

        while True:
            recordings = musicbrainzngs.browse_recordings(
                artist=artist_id, includes=["isrcs"], limit=batch_size, offset=offset
            )
            if not recordings["recording-list"]:
                break

            for recording in recordings["recording-list"]:
                title = recording["title"].lower()
                musicbrainz_id = recording["id"]
                isrcs = recording.get("isrc-list", [])
                songs[title] = {
                    "song_title": recording["title"],
                    "musicbrainz_id": musicbrainz_id,
                    "isrcs": isrcs,
                    "release_date": "Unknown Date",
                }

            offset += batch_size

        offset = 0
        while True:
            releases = musicbrainzngs.browse_releases(
                artist=artist_id,
                includes=["recordings"],
                limit=batch_size,
                offset=offset,
            )
            if not releases["release-list"]:
                break

            for release in releases["release-list"]:
                release_date = release.get("date", "Unknown Date")
                if "medium-list" in release:
                    for medium in release["medium-list"]:
                        for track in medium.get("track-list", []):
                            title = track["recording"]["title"].lower()
                            if title in songs:
                                songs[title]["release_date"] = release_date

            offset += batch_size

        print(f"Fetched {len(songs)} songs for artist ID: {artist_id}")
        return list(songs.values())
    except musicbrainzngs.ResponseError as e:
        raise Exception(f"Error fetching songs for artist ID {artist_id}: {e}")


@st.cache_data(persist="disk")
def get_songs_with_coauthors(artist_name: str) -> List[Dict]:
    """
    Fetch all songs by a given artist along with their co-authors and ISRC codes.

    Args:
        artist_name (str): The name of the artist.

    Returns:
        list: A list of dictionaries containing song titles, duration, co-authors, ISRC codes, and available markets.
    """
    print(f"Fetching songs with coauthors for: {artist_name}")
    try:
        artist_results = spotify.search(
            q=f"artist:{artist_name}", type="artist", limit=1
        )
        if not artist_results["artists"]["items"]:
            return []

        artist_id = artist_results["artists"]["items"][0]["id"]
        albums = spotify.artist_albums(artist_id, album_type="album,single", limit=50)
        album_ids = [album["id"] for album in albums["items"]]

        track_ids = []
        track_info = {}
        for album_id in album_ids:
            album_tracks = spotify.album_tracks(album_id)
            for track in album_tracks["items"]:
                track_ids.append(track["id"])
                track_info[track["id"]] = {
                    "song_title": track["name"],
                    "duration": track["duration_ms"],
                    "coauthors": [
                        {"name": artist["name"], "id": artist["id"]}
                        for artist in track["artists"]
                        if artist["name"].lower() != artist_name.lower()
                    ],
                    "available_markets": track["available_markets"],
                }

        # Function to split list into batches of a specified size
        def batch_list(lst, batch_size):
            for i in range(0, len(lst), batch_size):
                yield lst[i : i + batch_size]

        songs_with_coauthors = []
        for batch in batch_list(track_ids, 50):
            tracks_details = spotify.tracks(batch)
            for track in tracks_details["tracks"]:
                track_id = track["id"]
                isrc_code = track.get("external_ids", {}).get(
                    "isrc", "No ISRC available"
                )
                track_data = track_info[track_id]
                track_data["isrc"] = isrc_code
                songs_with_coauthors.append(track_data)

        print(
            f"Fetched {len(songs_with_coauthors)} songs with coauthors for: {artist_name}"
        )
        return songs_with_coauthors
    except Exception as e:
        raise Exception(f"Error fetching songs with coauthors for {artist_name}: {e}")


def fetch_coauthor_songs_and_info(coauthors: List[Dict]):
    """
    Fetch songs and artist information for all unique coauthors.

    Args:
        coauthors (list): List of unique coauthors with their names and IDs.

    Returns:
        dict: A dictionary with coauthor IDs as keys and their info and songs as values.
    """
    coauthor_data = {}

    for coauthor in coauthors:
        name = coauthor["name"]
        coauthor_id = coauthor["id"]

        print(f"Fetching data for coauthor: {name} ({coauthor_id})")
        try:
            artist_info = get_artist_info(name)
            coauthor_songs = get_songs_with_coauthors(name)
            coauthor_data[coauthor_id] = {
                "artist_info": artist_info,
                "songs": coauthor_songs,
            }
        except Exception as e:
            print(f"Error fetching data for coauthor {name} ({coauthor_id}): {e}")

    return coauthor_data


def get_unique_coauthors(songs_with_coauthors: List[Dict]) -> List[Dict]:
    """
    Extract unique coauthors and their IDs from the songs_with_coauthors list.

    Args:
        songs_with_coauthors (list): List of songs with coauthors information.

    Returns:
        list: A list of unique coauthors with their names and IDs.
    """
    coauthor_set = set()
    unique_coauthors = []

    for song in songs_with_coauthors:
        for coauthor in song.get("coauthors", []):
            coauthor_tuple = (coauthor["name"], coauthor["id"])
            if coauthor_tuple not in coauthor_set:
                coauthor_set.add(coauthor_tuple)
                unique_coauthors.append(coauthor)

    return unique_coauthors


def save_to_json(data: dict, filename: str) -> None:
    """
    Save data to a JSON file.

    Args:
        data (dict): The data to save.
        filename (str): The filename for the JSON file.
    """
    with open(os.path.join(SAVE_FOLDER, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_from_json(filename: str) -> dict:
    """
    Load data from a JSON file.

    Args:
        filename (str): The filename for the JSON file.

    Returns:
        dict: The loaded data.
    """
    try:
        with open(os.path.join(SAVE_FOLDER, filename), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"{filename} not found. Skipping load.")
        return {}


def get_top_coauthors(songs_with_coauthors: List[Dict], top_n: int = 5) -> List[Dict]:
    """
    Extract the top N most frequent coauthors from the songs_with_coauthors list.

    Args:
        songs_with_coauthors (list): List of songs with coauthors information.
        top_n (int): Number of top coauthors to return.

    Returns:
        list: A list of the top N coauthors with their names and IDs.
    """
    coauthor_count = Counter()

    # Count the frequency of each coauthor
    for song in songs_with_coauthors:
        for coauthor in song.get("coauthors", []):
            coauthor_count[(coauthor["name"], coauthor["id"])] += 1

    # Get the top N most frequent coauthors
    top_coauthors = [
        {"name": name, "id": coauthor_id, "count": coauthor_count[(name, coauthor_id)]}
        for (name, coauthor_id), _ in coauthor_count.most_common(top_n)
    ]

    return top_coauthors


def preprocess_isrcs(songs: List[Dict]) -> List[Dict]:
    """
    Preprocess the ISRC codes for each song, extracting only the first ISRC if multiple are available.

    Args:
        songs (list): A list of song dictionaries containing ISRC codes.

    Returns:
        list: A list of song dictionaries with preprocessed ISRC codes.
    """
    for i in range(len(songs)):
        songs[i]["isrc"] = songs[i]["isrcs"][0] if len(songs[i]["isrcs"]) != 0 else None
        songs[i].pop("isrcs", None)
    return songs


def get_artist_data(artist_name: Optional[str] = None, save_info: bool = False):
    """
    Main function to orchestrate the fetching, preprocessing, saving, loading,
    and timing of artist and song data.
    """
    try:
        # Step 1: Fetch artist information
        print("Fetching artist information...")
        start_time = time.time()
        if artist_name:
            artist_info = get_artist_info(artist_name)
            if save_info:
                save_to_json(artist_info, "artist_info.json")
        else:
            artist_info = load_from_json("artist_info.json")
        print(f"Artist Info: {artist_info}")
        print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

        # Step 2: Fetch songs from artist
        print("Fetching songs...")
        start_time = time.time()
        if artist_name:
            songs = get_songs_from_artist(artist_info["artist_id"])
            if save_info:
                save_to_json(songs, "songs.json")
        else:
            songs = load_from_json("songs.json")
        print(f"Total Songs: {len(songs)}")
        print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

        # Step 3: Preprocess ISRC codes
        print("Preprocessing ISRC codes...")
        start_time = time.time()
        if artist_name:
            songs = preprocess_isrcs(songs)
            if save_info:
                save_to_json(songs, "songs_preprocessed.json")
        else:
            songs = load_from_json("songs_preprocessed.json")
        print(
            f"Sample Song After ISRC Preprocessing: {songs[0] if songs else 'No Songs Found'}"
        )
        print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

        # Step 4: Fetch songs with co-authors
        print("Fetching songs with co-authors...")
        start_time = time.time()
        if artist_name:
            songs_with_coauthors = get_songs_with_coauthors(artist_name)
            if save_info:
                save_to_json(songs_with_coauthors, "songs_with_coauthors.json")
        else:
            songs_with_coauthors = load_from_json("songs_with_coauthors.json")
        print(f"Total Songs with Co-authors: {len(songs_with_coauthors)}")
        print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

        # Step 5: Get top 5 coauthors
        print("Extracting top 5 coauthors...")
        start_time = time.time()
        top_coauthors = get_top_coauthors(songs_with_coauthors, top_n=5)
        if save_info:
            save_to_json(top_coauthors, "top_coauthors.json")
        print(f"Top 5 Coauthors: {[coauthor['name'] for coauthor in top_coauthors]}")
        print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

        # Step 6: Fetch top coauthors' songs and information
        print("Fetching top coauthors' songs and artist information...")
        start_time = time.time()
        if artist_name:
            coauthor_data = fetch_coauthor_songs_and_info(top_coauthors)
            if save_info:
                save_to_json(coauthor_data, "coauthor_data.json")
        else:
            coauthor_data = load_from_json("coauthor_data.json")
        print(f"Fetched data for {len(coauthor_data)} coauthors.")
        print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

        main_artist_data = {
            "artist_info": artist_info,
            "songs": songs,
            "songs_with_coauthors": songs_with_coauthors,
        }
        return main_artist_data, coauthor_data
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    artist_name = "Kendrick Lamar"
    main_artist_info, coauthor_data = get_artist_data(artist_name, True)
