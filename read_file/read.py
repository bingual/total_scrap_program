import asyncio
import os
import re

import pandas as pd

from scraper.scrap_crawlers import (
    ScrapGiftKakao,
    ScrapNaverBrandStore,
    ScrapHM,
    ScrapZARA,
)
from scraper.utils import (
    setup_asyncio,
    BASE_DIR,
    update_image_sources,
    setup_datetime,
    create_xlsx_file,
    save_to_xlsx,
    DEFAULT_DIR_NAME,
)

setup_asyncio()


# 수동 업데이트
class Read:
    root_path = BASE_DIR.parent / "read_file"
    excel = "excel"
    images = "images"

    @classmethod
    async def update_image_match(cls):
        file_name = ""
        extension = ".xlsx"
        timestamp = setup_datetime()
        file_path = cls.root_path / cls.excel / f"{file_name}_{timestamp}{extension}"

        image_dir = cls.root_path / cls.images / f"{file_name}_{timestamp}"

        all_files = os.listdir(image_dir)
        image_num_list = []
        for file_name in all_files:
            if file_name.endswith((".jpg", ".png", ".gif")):
                match = re.search(r"_(\d+)\.", file_name)
                if match:
                    num = match.group(1)
                    image_num_list.append(int(num) - 1)

        await update_image_sources(
            file_path=file_path,
            image_num_list=image_num_list,
        )

    # TODO: 엑셀 업데이트 자동화 테스트
    @classmethod
    async def update_xlsx(cls):
        file_name = "test"
        extension = ".xlsx"
        timestamp = setup_datetime()
        file_path = cls.root_path / cls.excel / f"{file_name}{extension}"
        df = pd.read_excel(file_path)

        xlsx_site_names = df["사이트"].unique()

        scrapers = {
            ScrapGiftKakao().site_name: ScrapGiftKakao(),
            ScrapNaverBrandStore().site_name: ScrapNaverBrandStore(),
            ScrapHM().site_name: ScrapHM(),
            ScrapZARA().site_name: ScrapZARA(),
        }

        new_columns = ["차액", "변경옵션1", "변경옵션2", "변경상품명", "품절"]
        for col in new_columns:
            if col not in df.columns:
                df[col] = ""

        scrap_datas = []
        for xlsx_site_name in xlsx_site_names:
            filtered_df = df[df["사이트"] == xlsx_site_name]
            product_urls = [
                {category: link}
                for category, link in zip(filtered_df["카테고리"], filtered_df["링크"])
            ]
            scrap_data = {xlsx_site_name: product_urls}
            scrap_datas.append(scrap_data)

        for scrap_data in scrap_datas:
            for site_name, product_urls in scrap_data.items():
                product_details, _ = await scrapers[site_name].update(
                    product_urls=product_urls
                )

                for product_detail in product_details:
                    link = product_detail["링크"]
                    matching_row = df[df["링크"] == link]

                    if not matching_row.empty:
                        index = matching_row.index[0]

                        # Check and update 상품명
                        if df.at[index, "상품명"] != product_detail["상품명"]:
                            df.at[index, "변경상품명"] = product_detail["상품명"]

                        # Check and update 판매가 and 차액
                        if df.at[index, "판매가"] != product_detail["판매가"]:
                            df.at[index, "차액"] = max(
                                df.at[index, "판매가"], product_detail["판매가"]
                            ) - min(df.at[index, "판매가"], product_detail["판매가"])
                            df.at[index, "판매가"] = product_detail["판매가"]

                        # Check and update 옵션1
                        if df.at[index, "옵션1"] != product_detail["옵션1"]:
                            df.at[index, "변경옵션1"] = product_detail["옵션1"]

                        # Check and update 옵션2
                        if df.at[index, "옵션2"] != product_detail["옵션2"]:
                            df.at[index, "변경옵션2"] = product_detail["옵션2"]

                        # 품절 컬럼은 빈 값으로 생성
                        df.at[index, "품절"] = ""

        excel_buffer = await create_xlsx_file(
            data=df.to_dict("records"), file_name=file_name, sheet_name=DEFAULT_DIR_NAME
        )
        output_path = cls.root_path / cls.excel
        await save_to_xlsx(xlsx_file=excel_buffer, output_path=output_path)


asyncio.run(Read.update_xlsx())
