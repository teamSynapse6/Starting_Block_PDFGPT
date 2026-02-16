import requests


def information_from_pdf_server(announcement_id: int) -> str:
    pdf_url = f"https://pdfgpt.startingblock.co.kr/announcement?id={announcement_id}"
    response = requests.get(pdf_url, timeout=15)

    if response.status_code == 200:
        return response.content.decode("utf-8")
    if response.status_code == 404:
        return "요청하신 정보를 찾을 수 없습니다."
    return "서버에서 정보를 검색하는 동안 오류가 발생했습니다."
