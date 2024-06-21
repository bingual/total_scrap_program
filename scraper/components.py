import asyncio
from typing import Tuple

import flet as ft

from scraper.scrap_crawlers import (
    ScrapMain,
    ScrapNaverBrandStore,
    ScrapGiftKakao,
    ScrapDior,
    ScrapHM,
    ScrapZARA,
    ScrapGooglePlayReView,
    ScrapValentino,
    ScrapBottegaveneta,
    ScrapSaintLaurent,
    ScrapBalenciaga,
)
from scraper.utils import (
    get_logger,
    get_error_message,
    read_data_info_excel_and_download_images,
    setup_asyncio,
)

setup_asyncio()


class FletUtilComponent:
    def __init__(self, page: ft.Page):
        self.page = page

        self.dialog_text = ft.Text()
        self.dlg = ft.AlertDialog(title=self.dialog_text)

        self.progress_text = ft.Text(
            visible=False, value="작업이 진행되는 동안 창을 닫지 마세요."
        )
        self.progress_bar = ft.ProgressBar(height=10, visible=False, expand=True)

        self.cancel_button = ft.ElevatedButton(
            text="작업 중지",
            on_click=self.cancel_task,
            expand=True,
            visible=False,
        )

        self.task = None  # 작업을 추적할 Task 객체

    async def start_task(self, task_func, start_button):
        self.progress_text.visible = True
        self.progress_bar.visible = True
        self.cancel_button.visible = True

        start_button.disabled = True  # 시작 버튼 비활성화
        self.page.update()

        self.page.dialog = self.dlg
        self.task = asyncio.create_task(task_func())

        try:
            await self.task
            message = "완료되었습니다."
            print(message)
            self.dialog_text.value = message
            self.dlg.open = True

        except asyncio.CancelledError:
            message = "작업이 중지되었습니다."
            print(message)
            self.dialog_text.value = message
            self.dlg.open = True

        except Exception as e:
            message = "에러가 발생했습니다."
            print(message)
            self.dialog_text.value = message
            self.dlg.open = True

            logger = await get_logger()
            logger.error(await get_error_message())
            raise e

        finally:
            self.progress_text.visible = False
            self.progress_bar.visible = False
            self.cancel_button.visible = False

            start_button.disabled = False  # 작업 완료 후 시작 버튼 활성화
            self.page.update()

    async def cancel_task(self, e):
        if self.task:
            self.task.cancel()


class ScrapComponent(FletUtilComponent):
    def __init__(self, page: ft.Page):
        super().__init__(page)
        self.scrap_label = ft.Text(
            "스크랩",
            size=30,
        )

        self.scrap_label_total = ft.Text("종합 스크랩", size=15)
        self.scrap_label_luxury = ft.Text("명품 스크랩", size=15)
        self.scrap_label_review = ft.Text("리뷰 스크랩", size=15)

        self.init_product_no = ft.TextField(
            label="시작 상품번호",
            input_filter=ft.NumbersOnlyInputFilter(),
            value="1",
            max_length=7,
            expand=True,
        )

        self.start_button = ft.FilledButton(
            text="스크랩 작업 시작",
            on_click=self.start_scrap,
            expand=True,
        )

        # 종합
        self.scrap_kakao = ft.Checkbox(label=ScrapGiftKakao().site_name, value=False)
        self.scrap_naver = ft.Checkbox(
            label=ScrapNaverBrandStore().site_name, value=False
        )
        self.scrap_hm = ft.Checkbox(label=ScrapHM().site_name, value=False)
        self.scrap_zara = ft.Checkbox(label=ScrapZARA().site_name, value=False)

        # 명품
        self.scrap_dior = ft.Checkbox(
            label=ScrapDior().site_name,
            value=False,
            disabled=True,
        )  # FIXME: 안티봇
        self.scrap_valentino = ft.Checkbox(
            label=ScrapValentino().site_name, value=False
        )
        self.scrap_bottegaveneta = ft.Checkbox(
            label=ScrapBottegaveneta().site_name, value=False
        )
        self.scrap_saint_laurent = ft.Checkbox(
            label=ScrapSaintLaurent().site_name, value=False
        )
        self.scrap_balenciaga = ft.Checkbox(
            label=ScrapBalenciaga().site_name, value=False
        )
        # 리뷰
        self.scrap_google_play_review = ft.Checkbox(
            label=ScrapGooglePlayReView().site_name, value=False
        )

    async def is_valid(self) -> Tuple[bool, str]:

        if not self.init_product_no.value:
            return False, ""

        init_product_no_valid = int(self.init_product_no.value) >= 1

        scrap_sites_valid = any(
            [
                # 종합
                self.scrap_kakao.value,
                self.scrap_naver.value,
                self.scrap_hm.value,
                self.scrap_zara.value,
                # 명품
                self.scrap_dior.value,
                self.scrap_valentino.value,
                self.scrap_bottegaveneta.value,
                self.scrap_saint_laurent.value,
                self.scrap_balenciaga.value,
            ]
        )

        scrap_sites_review_valid = any(
            # 리뷰
            [
                self.scrap_google_play_review.value,
            ]
        )

        if init_product_no_valid and scrap_sites_valid and not scrap_sites_review_valid:
            return True, "Product"

        if scrap_sites_valid ^ scrap_sites_review_valid:
            return True, "Review"

        return False, ""

    async def scrap_product_task(self):
        scrap_mapping = {
            # 종합
            self.scrap_kakao: ScrapGiftKakao,
            self.scrap_naver: ScrapNaverBrandStore,
            self.scrap_hm: ScrapHM,
            self.scrap_zara: ScrapZARA,
            # 명품
            self.scrap_dior: ScrapDior,
            self.scrap_valentino: ScrapValentino,
            self.scrap_bottegaveneta: ScrapBottegaveneta,
            self.scrap_saint_laurent: ScrapSaintLaurent,
            self.scrap_balenciaga: ScrapBalenciaga,
        }

        scrap_instances = []
        for checkbox, scraper_class in scrap_mapping.items():
            if checkbox.value:
                scrap_instances.append(scraper_class)

        await ScrapMain(
            init_product_no=int(self.init_product_no.value),
            scrap_instances=scrap_instances,
        ).main()

    async def scrap_review_task(self):
        scrap_mapping = {
            # 리뷰
            self.scrap_google_play_review: ScrapGooglePlayReView,
        }

        scrap_instances = []
        for checkbox, scraper_class in scrap_mapping.items():
            if checkbox.value:
                scrap_instances.append(scraper_class)

        for scrap_instance in scrap_instances:
            await scrap_instance().create()

    async def start_scrap(self, e):
        valid, state = await self.is_valid()

        if valid and state == "Product":
            await asyncio.create_task(
                self.start_task(self.scrap_product_task, self.start_button)
            )
        elif valid and state == "Review":
            await asyncio.create_task(
                self.start_task(self.scrap_review_task, self.start_button)
            )
        else:
            await show_snack_bar(
                self.page,
                "시작 상품번호 및 스크랩 목록을 확인하세요.",
                ft.colors.RED_400,
            )

    def get_controls(self):
        return [
            ft.Row(controls=[self.scrap_label]),
            # 종합
            ft.Row(controls=[self.scrap_label_total]),
            ft.Row(
                controls=[
                    self.scrap_kakao,
                    self.scrap_naver,
                    self.scrap_hm,
                    self.scrap_zara,
                ]
            ),
            # 명품
            ft.Row(controls=[self.scrap_label_luxury]),
            ft.Row(
                controls=[
                    self.scrap_dior,
                    self.scrap_valentino,
                    self.scrap_bottegaveneta,
                    self.scrap_saint_laurent,
                    self.scrap_balenciaga,
                ]
            ),
            # 리뷰
            ft.Row(controls=[self.scrap_label_review]),
            ft.Row(
                controls=[
                    self.scrap_google_play_review,
                ]
            ),
            ft.Row(controls=[self.init_product_no]),
            ft.Row(controls=[self.start_button]),
            ft.Row(controls=[self.cancel_button]),
            ft.Row(controls=[self.progress_text]),
            ft.Row(controls=[self.progress_bar]),
        ]


class ImageUpdateComponent(FletUtilComponent):
    def __init__(self, page: ft.Page):
        super().__init__(page)
        self.image_update_label = ft.Text("이미지 업데이트", size=30)

        self.pick_files_dialog = ft.FilePicker(on_result=self.pick_files_result)
        self.page.overlay.append(self.pick_files_dialog)

        self.selected_files = ft.TextField(
            label="엑셀 파일", expand=True, read_only=True, helper_text="읽기 전용"
        )
        self.initialize_file = ft.ElevatedButton(
            "파일 초기화",
            icon=ft.icons.CLEAR,
            on_click=self.clear_files,
        )

        # self.sheet_name = ft.TextField(
        #     label="엑셀 시트",
        #     expand=True,
        #     helper_text="엑셀 시트 이름을 입력해주세요. 정확하지 않으면 에러가 발생합니다.",
        # )

        self.upload_file = ft.FilledButton(
            "엑셀 업로드",
            icon=ft.icons.UPLOAD_FILE,
            on_click=lambda _: self.pick_files_dialog.pick_files(
                allow_multiple=False, allowed_extensions=["xlsx"]
            ),
            expand=True,
        )
        self.update_image = ft.FilledButton(
            "이미지 업데이트 시작",
            on_click=self.start_image_update,
            expand=True,
        )

    async def pick_files_result(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.selected_files.value = e.files[0].path
            self.selected_files.update()

    async def clear_files(self, e):
        self.selected_files.value = ""
        self.selected_files.update()

    async def is_valid(self) -> str | None:
        selected_files = self.selected_files.value
        # sheet_name = self.sheet_name.value

        return selected_files

    async def image_update_task(self):
        await read_data_info_excel_and_download_images(
            file_path=self.selected_files.value,
            # sheet_name=self.sheet_name.value,
        )

    async def start_image_update(self, e):
        if await self.is_valid():
            await asyncio.create_task(
                self.start_task(self.image_update_task, self.update_image)
            )
        else:
            await show_snack_bar(
                self.page, "엑셀 파일을 업로드해주세요.", ft.colors.RED_400
            )

    def get_controls(self):
        return [
            ft.Row(controls=[self.image_update_label]),
            # ft.Row(controls=[self.sheet_name]),
            ft.Row(controls=[self.selected_files, self.initialize_file]),
            ft.Row(controls=[self.upload_file, self.update_image]),
            ft.Row(controls=[self.cancel_button]),
            ft.Row(controls=[self.progress_text]),
            ft.Row(controls=[self.progress_bar]),
        ]


async def show_snack_bar(page: ft.Page, text: str, color: str):
    page.snack_bar = ft.SnackBar(ft.Text(text), bgcolor=color)
    page.snack_bar.open = True
    page.update()
