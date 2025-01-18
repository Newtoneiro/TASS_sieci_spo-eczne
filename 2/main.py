from pyvis import network as net
from dateutil import parser as dateparser
from datetime import datetime
import traceback
import streamlit as st
import streamlit.components.v1 as components
import networkx as nx
from collections import deque
from get_data import (
    get_artist_info,
    get_songs_with_coauthors,
    get_top_coauthors,
    filter_coauthor,
)


st.set_page_config(page_title="Artist Collaboration Explorer", layout="wide")
st.title("🎵 Artist Collaboration Explorer")


artist_name = st.text_input(
    "Enter Artist Name:",
    value="Kendrick Lamar",
    placeholder="e.g., Kendrick Lamar",
    key="artist_name_input",
)


if artist_name:
    try:
        # Fetch artist info
        st.header(f"🎤 {artist_name} Information")
        artist_info = get_artist_info(artist_name)

        if artist_info:
            col1, col2 = st.columns([1, 2])

            with col1:
                st.subheader("Basic Info")
                st.write(f"**Name:** {artist_info.get('artist_name', 'N/A')}")
                st.write(
                    f"**Origin Country:** {artist_info.get('origin_country', 'N/A')}"
                )
                st.write(
                    f"**Life Span:** {artist_info.get('life_span', {}).get('begin', 'Unknown')} - {artist_info.get('life_span', {}).get('end', 'Present')}"
                )

            with col2:
                tags = artist_info.get("tags", [])
                if tags:
                    st.subheader("Top Tags")
                    tag_names = [tag.get("name", "N/A") for tag in tags]
                    selected_tags = st.multiselect(
                        "", options=tag_names, default=tag_names
                    )

        # Fetch songs with coauthors
        st.header("🎶 Example songs with Coauthors")
        songs_with_coauthors = get_songs_with_coauthors(artist_name)

        if songs_with_coauthors:
            top_songs = sorted(
                songs_with_coauthors,
                key=lambda x: len(x.get("coauthors", [])),
                reverse=True,
            )[:10]

            for song in top_songs:
                song_title = song["song_title"].split("(")[0]
                separator = "".join([" " for _ in range(25 - len(song_title))])
                song_title = f"{song_title}{separator} ||"
                coauthors = " | ".join(
                    [f"🤝 {coauthor['name']}" for coauthor in song.get("coauthors", [])]
                )
                st.text(f"- 🎵 {song_title} {coauthors}")

        # Top coauthors
        st.header("🤝 Top Coauthors")

        n_coauthors = st.number_input("No. top authors", min_value=0, value=5)
        top_coauthors = get_top_coauthors(songs_with_coauthors, top_n=n_coauthors)

        if top_coauthors:
            st.write(f"Here are the top {n_coauthors} coauthors:")
            col1, col2 = st.columns(2)
            for idx, coauthor in enumerate(top_coauthors):
                coauthor_info = f"🤝 {coauthor['name']}"
                if idx % 2 == 0:
                    with col1:
                        st.write(coauthor_info)
                else:
                    with col2:
                        st.write(coauthor_info)

        # Graph visualization with n levels and n authors in levels
        st.header("📊 Artist Collaboration Network")

        n_authors_in_level = st.slider(
            "Number of authors on each level", min_value=1, max_value=20, value=5
        )
        n_levels = st.slider(
            "Number of levels of collaboration", min_value=1, max_value=5, value=2
        )

        st.header("Filters")

        # Predefine filters here
        filters = [
            (
                "Genre",
                tag_names,
                lambda coauthor_info, v: v
                in [tag["name"] for tag in coauthor_info["tags"]],
                "eg. rap",
            ),
            (
                "Country",
                "text_input",
                lambda coauthor_info, v: (
                    v.lower().strip() == coauthor_info["origin_country"].lower().strip()
                    if coauthor_info.get("origin_country", None) is not None
                    and v is not None
                    else False
                ),
                "eg. United States",
            ),
            (
                "Artist born after / Band created after",
                "text_input",
                lambda coauthor_info, v: (
                    dateparser.parse(coauthor_info["life_span"]["begin"])
                    > datetime(int(v), 12, 31, 23, 59, 59)
                    if v is not None
                    and v.strip().isnumeric()
                    and coauthor_info.get("life_span", None) not in [None, {}]
                    and coauthor_info["life_span"].get("begin", None) is not None
                    else False
                ),
                "eg. 1990",
            ),
            (
                "Career ended",
                ["true", "false"],
                lambda coauthor_info, v: (
                    v.lower().strip()
                    == coauthor_info["life_span"]["ended"].lower().strip()
                    if coauthor_info.get("life_span", None) not in [None, {}]
                    and coauthor_info["life_span"].get("ended", None) is not None
                    and v is not None
                    else False
                ),
                "eg. true/false",
            ),
        ]
        filters_st = {}

        for filter_title, filter_values, filter_func, filter_placeholder in filters:
            if isinstance(filter_values, list):
                filters_st[filter_title] = (
                    st.selectbox(
                        f"Filter by {filter_title}",
                        [None] + filter_values,
                        placeholder=filter_placeholder,
                    ),
                    filter_func,
                )
            elif filter_values == "text_input":
                filters_st[filter_title] = (
                    st.text_input(
                        f"Search by {filter_title}",
                        placeholder=filter_placeholder,
                    ),
                    filter_func,
                )

        with st.spinner("Generating the graph..."):
            artist_name = artist_name.lower()

            visited = set([artist_name])
            levels = {artist_name: 0}
            queue = deque([(artist_name, 0)])  # (artist, level)

            level_colors = [
                "#b30000",
                "#0A369D",
                "#4472CA",
                "#92B4F4",
                "#B1C9EE",
                "#C0D4EB",
                "#CFDEE7",
            ]
            node_size_multiplayer = 5
            max_node_size = 40

            G = nx.Graph()
            G.add_node(
                artist_name,
                color=level_colors[0],
                title=f"{artist_name}\nOrigin: {artist_info.get('origin_country', 'N/A')}\nLife Span: {artist_info.get('life_span', {}).get('begin', 'Unknown')} - {artist_info.get('life_span', {}).get('end', 'Present')}",
            )

            while queue:
                current_artist, level = queue.popleft()
                current_artist = current_artist.lower()
                if level < n_levels:
                    songs_with_coauthors = get_songs_with_coauthors(current_artist)
                    top_coauthors = get_top_coauthors(
                        songs_with_coauthors, top_n=n_authors_in_level
                    )
                    for coauthor in top_coauthors:
                        coauthor_name = coauthor["name"]
                        coauthor_info = get_artist_info(coauthor_name)
                        if not filter_coauthor(
                            coauthor_info,
                            [
                                (val, func)
                                for val, func in filters_st.values()
                                if val is not None
                            ],
                        ):
                            continue
                        coauthor_name = coauthor_name.lower()
                        if coauthor_name not in visited:
                            G.add_node(
                                coauthor_name,
                                color=level_colors[level + 1],
                                size=min(
                                    node_size_multiplayer * coauthor["count"],
                                    max_node_size,
                                ),
                                title=f"{coauthor_name}\nOrigin: {coauthor_info.get('origin_country', 'N/A')}\nLife Span: {coauthor_info.get('life_span', {}).get('begin', 'Unknown')} - {coauthor_info.get('life_span', {}).get('end', 'Present')}",
                            )
                            visited.add(coauthor_name)
                            levels[coauthor_name] = level + 1
                            queue.append((coauthor_name, level + 1))
                        if coauthor_name not in [
                            artist_name,
                            current_artist,
                        ]:
                            G.add_edge(
                                current_artist,
                                coauthor_name,
                                label=f"{coauthor['count']} co.",
                                font={"size": 10},
                            )
        # Create the graph visualization
        pos = nx.spring_layout(G, k=0.15, iterations=30)
        nx.draw_networkx_edges(G, pos, width=2, alpha=0.5, edge_color="gray")
        nx.draw_networkx_labels(G, pos, font_size=8, font_color="black")
        _, col, _ = st.columns([1, 2, 1])

        with col:
            interactive_g = net.Network(height="900px")
            interactive_g.from_nx(G)
            interactive_g.write_html("example.html")

        HtmlFile = open("example.html", "r", encoding="utf-8")
        source_code = HtmlFile.read()
        components.html(source_code, height=900)

    except Exception as e:
        print(traceback.format_exc())
        st.error(f"An error occurred: {e}")
