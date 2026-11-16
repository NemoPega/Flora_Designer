import os
import re
from urllib.parse import parse_qs, urlparse

import requests
import streamlit as st


MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "https://hook.eu1.make.com/r354vna1ou5x4boe3ov2fffis852attd")


def drive_url_for_display(url):
    parsed_url = urlparse(url)
    if parsed_url.hostname not in {"drive.google.com", "www.drive.google.com"}:
        return url

    file_id = None
    path_parts = parsed_url.path.split("/")
    if "d" in path_parts:
        file_id_index = path_parts.index("d") + 1
        if file_id_index < len(path_parts):
            file_id = path_parts[file_id_index]
    if not file_id:
        file_id = parse_qs(parsed_url.query).get("id", [None])[0]

    if file_id:
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1200"
    return url


def extract_image_urls(payload):
    image_urls = []

    def collect(value, key=""):
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                collect(child_value, child_key.lower())
        elif isinstance(value, list):
            for item in value:
                collect(item, key)
        elif isinstance(value, str):
            has_image_field = (
                key in {"image", "images", "file", "link"}
                or key.endswith(("url", "urls", "link"))
            )
            urls = re.findall(r"https?://[^\s\"'<>]+", value)
            if not has_image_field and value.strip().startswith(("https://", "http://")):
                urls = [value.strip()]
            if has_image_field or value is payload:
                for url in urls:
                    image_urls.append(drive_url_for_display(url.rstrip(".,);")))

    collect(payload)
    return list(dict.fromkeys(image_urls))


def fetch_image(image_url):
    response = requests.get(image_url, timeout=30)
    response.raise_for_status()
    mime_type = response.headers.get("Content-Type", "").split(";")[0]
    if not mime_type.startswith("image/"):
        raise ValueError("The link did not return an image. Check its Google Drive sharing settings.")
    return response.content, mime_type


def image_filename(index, mime_type):
    extension = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(mime_type, "img")
    return f"generated_image_{index}.{extension}"


@st.dialog("Image Viewer", width="large")
def show_image_viewer(image):
    image_data = image.get("data")
    st.image(image_data or image["url"], caption=image["prompt"], use_container_width=True)
    if image_data:
        st.download_button(
            "Download image",
            data=image_data,
            file_name=image["filename"],
            mime=image["mime_type"],
            key=f"viewer_download_{image['filename']}",
            use_container_width=True,
        )
    else:
        st.link_button("Open original image", image["url"], use_container_width=True)


if "gallery" not in st.session_state:
    st.session_state.gallery = []

st.title("AI Image Generator")
prompt = st.text_input("Enter your prompt:")

if st.button("Generate"):
    if not prompt.strip():
        st.warning("Enter a prompt first.")
    elif not MAKE_WEBHOOK_URL:
        st.error("Set the MAKE_WEBHOOK_URL environment variable to your Make.com webhook URL.")
    else:
        try:
            response = requests.post(
                MAKE_WEBHOOK_URL,
                json={"Prompt": prompt.strip()},
                timeout=120,
            )
            response.raise_for_status()
            try:
                response_data = response.json()
                
            except ValueError:
                response_data = response.text

            image_urls = extract_image_urls(response_data)
            if image_urls:
                for image_url in image_urls:
                    try:
                        image_data, mime_type = fetch_image(image_url)
                    except (requests.RequestException, ValueError) as error:
                        image_data, mime_type = None, None
                        st.warning(f"Image received, but it could not be prepared for download: {error}")

                    image_index = len(st.session_state.gallery) + 1
                    st.session_state.gallery.insert(
                        0,
                        {
                            "url": image_url,
                            "prompt": prompt.strip(),
                            "data": image_data,
                            "mime_type": mime_type,
                            "filename": image_filename(image_index, mime_type or ""),
                        },
                    )
                st.success(f"Added {len(image_urls)} image(s) to the gallery.")
            else:
                st.warning(
                    "Make.com completed the request but returned no image URL. "
                    "Add a Webhook Response module after the Google Drive upload "
                    "and return JSON with an image_url or image_urls field."
                )
        except requests.RequestException as error:
            st.error(f"Could not generate images: {error}")

st.subheader("Gallery")
if not st.session_state.gallery:
    st.info("Generated images will appear here.")
else:
    columns = st.columns(3)
    for index, image in enumerate(st.session_state.gallery):
        with columns[index % len(columns)]:
            with st.container(border=True):
                st.image(
                    image.get("data") or image["url"],
                    caption=image["prompt"],
                    use_container_width=True,
                )
                view_column, download_column = st.columns(2)
                with view_column:
                    if st.button("View full size", key=f"view_{index}", use_container_width=True):
                        show_image_viewer(image)
                with download_column:
                    if image.get("data"):
                        st.download_button(
                            "Download",
                            data=image["data"],
                            file_name=image["filename"],
                            mime=image["mime_type"],
                            key=f"download_{index}",
                            use_container_width=True,
                        )
                    else:
                        st.link_button(
                            "Open original",
                            image["url"],
                            key=f"open_{index}",
                            use_container_width=True,
                        )