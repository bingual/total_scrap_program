import flet as ft

from scraper.components import ImageUpdateComponent, ScrapComponent
from scraper.utils import (
    setup_asyncio,
    setup_logging,
)

setup_asyncio()


async def main(page: ft.Page):
    page.title = "상품 관리 프로그램"

    page.window_width = 700
    # page.window_height = 700

    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    scrap = ScrapComponent(page)
    image_update = ImageUpdateComponent(page)

    page.add(
        ft.Column(
            controls=[
                *scrap.get_controls(),
                *image_update.get_controls(),
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    setup_logging()
    ft.app(target=main)
