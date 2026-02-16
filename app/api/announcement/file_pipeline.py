import fitz
import olefile
import zlib
import struct
import re


def detect_file_format(file_bytes: bytes) -> str:
    if file_bytes.startswith(b"%PDF"):
        return "pdf"
    if file_bytes.startswith(b"\xd0\xcf\x11\xe0"):
        return "hwp"
    if _is_text_file(file_bytes):
        return "txt"
    return "unknown"


def _is_text_file(file_bytes: bytes) -> bool:
    if not file_bytes:
        return True
    try:
        file_bytes.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def convert_pdf_bytes_to_text(file_bytes: bytes) -> str:
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text


def get_hwp_text_from_path(filename: str) -> str:
    with open(filename, "rb") as file:
        f = olefile.OleFileIO(file)
        dirs = f.listdir()

        header = f.openstream("FileHeader")
        header_data = header.read()
        is_compressed = (header_data[36] & 1) == 1

        nums = []
        for item in dirs:
            if item[0] == "BodyText":
                nums.append(int(item[1][len("Section"):]))
        sections = ["BodyText/Section" + str(number) for number in sorted(nums)]

        text = ""
        for section in sections:
            bodytext = f.openstream(section)
            data = bodytext.read()
            unpacked_data = zlib.decompress(data, -15) if is_compressed else data

            section_text = ""
            index = 0
            size = len(unpacked_data)
            while index < size:
                header = struct.unpack_from("<I", unpacked_data, index)[0]
                rec_type = header & 0x3FF
                rec_len = (header >> 20) & 0xFFF

                if rec_type == 67:
                    rec_data = unpacked_data[index + 4:index + 4 + rec_len]
                    try:
                        section_text += rec_data.decode("utf-16", errors="ignore")
                    except UnicodeDecodeError:
                        section_text += rec_data.decode("utf-16", errors="replace")
                    section_text += "\n"

                index += 4 + rec_len

            text += section_text
            text += "\n"

        return text


def convert_hwp_path_to_text(hwp_path: str) -> str:
    extracted_text = get_hwp_text_from_path(hwp_path)
    return re.sub(r"[^\w\s,.!?;:()가-힣]", "", extracted_text)
