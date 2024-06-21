import asyncio
import re
import urllib.parse
from typing import List, Tuple, Dict, Callable

from playwright.async_api import async_playwright, Page, Locator, Playwright, Browser
from tqdm.asyncio import tqdm

from scraper.utils import (
    convert_decimal,
    download_images,
    create_xlsx_file,
    save_to_xlsx,
    setup_asyncio,
    get_logger,
    convert_model,
    convert_string,
    BASE_DIR,
    get_error_message,
    setup_datetime,
)

setup_asyncio()


class ScrapUtil:
    def __init__(
        self,
        site_name: str = "",
        url: str = "",
        root_dirname: str = "",
        root_category: str = "",
        headless: bool = True,
        timeout: int = 15000,
        init_product_no: int = 1,
    ):
        self.site_name = site_name
        self.url = url
        self.root_category = root_category
        self.root_dirname = root_dirname

        self.headless = headless
        self.timeout = timeout
        self.init_product_no = init_product_no

        self.PRODUCT_URLS_DES = f"{self.site_name} 상품 페이지 링크 추출 중"
        self.PRODUCT_DETAILS_DES = f"{self.site_name} 상품 상세 정보 생성 중"

    async def setup_playwright(self, p: Playwright) -> Tuple[Browser, Page]:
        browser = await p.chromium.launch(channel="chrome", headless=self.headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            timezone_id="Asia/Seoul",
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        page = await context.new_page()
        await page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            navigator.plugins.length = 3;
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            """
        )
        page.set_default_timeout(self.timeout)

        return browser, page

    async def create(self) -> Tuple[List[dict], List[str]]:
        async with async_playwright() as p:
            try:
                browser, page = await self.setup_playwright(p)
                await page.goto(self.url)

                product_urls = await self.get_product_urls(page=page)
                product_details, product_image_urls = await self.get_product_details(
                    page=page, product_urls=product_urls
                )
            finally:
                await page.close()
                await browser.close()

        return product_details, product_image_urls

    async def update(
        self, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[str]]:
        async with async_playwright() as p:
            try:
                browser, page = await self.setup_playwright(p)
                await page.goto(self.url)

                result = await self.get_product_details(
                    page=page, product_urls=product_urls
                )

                product_details, product_image_urls = (
                    result if len(result) == 2 else (result[0], [])
                )
            finally:
                await page.close()
                await browser.close()

        return product_details, product_image_urls

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:
        return []

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[str]]:
        return [], []

    async def setup_screenshot(self, page: Page, category: str) -> None:
        try:
            timestamp = setup_datetime("%Y-%m-%d_%H_%M_%S")

            output_path = BASE_DIR / "screenshot" / self.site_name
            output_path.mkdir(parents=True, exist_ok=True)
            extension = ".png"

            screenshot_output = output_path / f"{category}_{timestamp}{extension}"
            await page.screenshot(path=screenshot_output)
        except Exception as e:
            setup_message = f"스크린샷 찍는 도중 예외 발생\n{await get_error_message()}"
            logger = await get_logger()
            logger.error(setup_message)
            print(setup_message)

    async def setup_product_error_log(
        self,
        page: Page,
        url: str,
        product_no: int,
        category: str = "",
        message: str = "",
        availability_screenshot: bool = True,
    ) -> None:
        if availability_screenshot:
            await self.setup_screenshot(page=page, category=category)

        setup_message = f"메세지: '{message}', 사이트: '{self.site_name}', 카테고리: '{category}', 상품번호: '{product_no}', 링크: '{url}'\n{await get_error_message()}"
        logger = await get_logger()
        logger.error(setup_message)
        print(setup_message)

    @classmethod
    async def scroll_to_the_bottom_old(
        cls, page: Page, interval: int = 200, sleep: float = 1
    ) -> None:
        await page.evaluate(
            f"""
                var intervalID = setInterval(function () {{
                    var scrollingElement = (document.scrollingElement || document.body);
                    scrollingElement.scrollTop = scrollingElement.scrollHeight;
                }}, {interval});
            """
        )
        prev_height = None
        while True:
            curr_height = await page.evaluate("(window.innerHeight + window.scrollY)")
            if not prev_height:
                prev_height = curr_height
                await asyncio.sleep(sleep)
            elif prev_height == curr_height:
                await page.evaluate("clearInterval(intervalID)")
                break
            else:
                prev_height = curr_height
                await asyncio.sleep(sleep)

    @classmethod
    async def scroll_to_the_bottom(
        cls, page: Page, interval: int = 1000, sleep: float = 1
    ) -> None:
        previous_height = await page.evaluate("window.scrollY")
        while True:
            await page.mouse.wheel(0, interval)
            await asyncio.sleep(sleep)

            new_height = await page.evaluate("window.scrollY")
            if new_height == previous_height:
                break

            previous_height = new_height

    @classmethod
    async def price_position_conversion(
        cls, origin_price_elem: Locator, sale_price_elem: Locator
    ) -> Tuple[int, int]:
        if await sale_price_elem.is_visible():
            origin_price = await convert_decimal(await sale_price_elem.inner_text())
            sale_price = await convert_decimal(await origin_price_elem.inner_text())
        else:
            origin_price = await convert_decimal(await origin_price_elem.inner_text())
            sale_price = await convert_decimal(await origin_price_elem.inner_text())
        return origin_price, sale_price

    @classmethod
    async def click_on_cookie_button(
        cls, page: Page, selector: str, sleep: float = 1
    ) -> None:
        await asyncio.sleep(sleep)
        cookie_button = page.locator(selector)

        if await cookie_button.is_visible():
            await cookie_button.scroll_into_view_if_needed()
            await cookie_button.click()

    @classmethod
    async def click_on_load_more_button(
        cls, page: Page, selector: str, sleep: float = 2
    ) -> None:
        load_more_button = page.locator(selector)

        while True:
            await asyncio.sleep(sleep)
            if await load_more_button.is_visible():
                await load_more_button.scroll_into_view_if_needed()
                await load_more_button.click()
            else:
                break


class ScrapMain:
    def __init__(
        self,
        scrap_instances: List[Callable],
        init_product_no: int = 1,
    ):
        self.scrap_instances = scrap_instances
        self.init_product_no = init_product_no

        self.total_product_details = []
        self.total_product_image_urls = []

    async def main(self) -> None:
        await self.scrap_selector()

        excel_file = await create_xlsx_file(
            data=self.total_product_details,
        )

        tasks = [
            save_to_xlsx(
                xlsx_file=excel_file,
            ),
            download_images(
                image_urls=self.total_product_image_urls,
                start_no=(
                    self.total_product_details[0]["상품번호"]
                    if self.total_product_details
                    else self.init_product_no
                ),
            ),
        ]
        await asyncio.gather(*tasks)

    async def scrap_selector(self) -> None:
        async def insert_scraped_data(scraper: Callable):
            product_details, product_image_urls = await scraper(
                init_product_no=self.init_product_no
            ).create()

            self.total_product_details.extend(product_details)
            self.total_product_image_urls.extend(product_image_urls)

            if product_details:
                self.init_product_no = product_details[-1]["상품번호"] + 1

        for instance in self.scrap_instances:
            await insert_scraped_data(instance)

        # 명품 시작


class ScrapValentino(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="발렌티노",
            url="https://www.valentino.com",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )
        self.categories = {
            "숄더백": "/ko-kr/women/bags?macroCategory=2138879",
            "클러치": "/ko-kr/women/bags?macroCategory=2138889",
            "탑 핸들 백": "/ko-kr/women/bags?macroCategory=2138885",
            "토트백": "/ko-kr/women/bags?macroCategory=2138883",
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:

        await self.click_on_cookie_button(
            page=page, selector="#onetrust-accept-btn-handler", sleep=1
        )

        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")

            await self.click_on_load_more_button(page=page, sleep=2)

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "#container-ce589f38ae > div.productlist > section > ul > li > div > a"
            ).all()

            for product_elem in product_elem_list:
                product_link = await product_elem.get_attribute("href")
                product_urls.append({category_key: f"{product_link}"})

        return product_urls

    async def get_product_details(self, page, product_urls: List[Dict[str, str]]):

        product_details = []
        product_image_urls = []

        async for i, product_url in tqdm(
            enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)
                    await page.wait_for_load_state()

                    brand = await page.locator(
                        "#container-76ee4dd134 > div.breadcrumb > div > section > ul > li.item.item__lv0 > a"
                    ).inner_text()
                    name = await page.locator(
                        "#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__left-container > "
                        "section.productInfo > article > h1"
                    ).inner_text()

                    model = await page.locator(
                        "#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__left-container > "
                        "section.accordion__section.accordion__wrapperContainer.productDescription.border-top-none > "
                        "div.content-tabs > div:nth-child(1) > p.productDescription__code"
                    ).inner_text()
                    model = await convert_model(model)

                    origin_price_elem = page.locator(
                        "#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__left-container > "
                        "section.productInfo > p > p.productInfo_price--markdown"
                    )
                    if await origin_price_elem.is_visible():
                        origin_price_element_index = 1
                        sale_price_element_index = 3
                    else:
                        origin_price_element_index = 1
                        sale_price_element_index = 1

                    origin_price = await page.locator(
                        f"#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__left-container > "
                        f"section.productInfo > p > p:nth-child({origin_price_element_index})"
                    ).inner_text()
                    sale_price = await page.locator(
                        f"#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__left-container > "
                        f"section.productInfo > p > p:nth-child({sale_price_element_index})"
                    ).inner_text()

                    origin_price, sale_price = await asyncio.gather(
                        convert_decimal(origin_price),
                        convert_decimal(sale_price),
                    )

                    option_1 = await page.locator(
                        "#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__right-container "
                        "> section.pdpColorSelection > div.pdpColorSelection__header > h2 > span"
                    ).first.inner_text()
                    option_2 = await page.locator(
                        "#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__right-container "
                        "> div.product_size_reactWrap.productSizeSelection.productSizeSelection--oneSize > ul > li > "
                        "label > p"
                    ).first.inner_text()

                    image_url_elem = page.locator(
                        "#container-76ee4dd134 > div.product > div > div.pdp-template__main-product__middle-container "
                        "> section.pdpSwiperProduct > div:not(.hidePDPSwiperProduct) > div.swiper-wrapper > "
                        "div.swiper-slide.swiper-slide-active > img"
                    )

                    if not await image_url_elem.get_attribute("src"):
                        image_url_elem = await image_url_elem.get_attribute(
                            "data-imgzoomed"
                        )
                    else:
                        image_url_elem = await image_url_elem.get_attribute("src")

                    if not image_url_elem:
                        await self.setup_product_error_log(
                            page=page,
                            url=url,
                            product_no=self.init_product_no + i,
                            message="상품 상세 페이지 이미지 로드 실패",
                        )

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": model.strip() if model else "",
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": option_1.strip(),
                        "옵션2": option_2.strip(),
                        "링크": url.strip(),
                        "이미지소스": image_url_elem.strip(),
                    }

                    product_details.append(product_detail_dict)
                    product_image_urls.append(image_url_elem)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        category=category,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details, product_image_urls

    @classmethod
    async def click_on_load_more_button(
        cls, page: Page, selector: str = None, sleep: float = 2
    ):
        while load_more_button := page.locator(
            "#container-ce589f38ae > div.productlist > section > div"
        ):
            await asyncio.sleep(sleep)
            is_hidden = await load_more_button.get_attribute("class")
            if is_hidden == "categoryListining__load-more hidden":
                break
            else:
                await load_more_button.scroll_into_view_if_needed()
                await asyncio.sleep(sleep)
                await load_more_button.get_by_role("button").click()


class ScrapDior(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="디올",
            url="https://www.dior.com",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )

        self.categories = {
            "탑핸들백": "/ko_kr/fashion/여성-패션/여성-가방/핸드백",
            "토트백": "/ko_kr/fashion/여성-패션/여성-가방/카바백",
            "크로스백 & 숄더백": "/ko_kr/fashion/여성-패션/여성-가방/크로스백-숄더백",
            "미니백": "/ko_kr/fashion/여성-패션/여성-가방/미니백-벨트백",
            "트래블": "/ko_kr/fashion/여성-패션/여성-가방/트래블",
            "핸드백 스트랩": "/ko_kr/fashion/여성-패션/여성-가방/스트랩",
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:

        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")
            await self.scroll_to_the_bottom(page, interval=1000, sleep=1)

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "#grid-products-list > ul > li.grid-item.col.col-sm-6.col-md-4 a"
            ).all()

            for product_elem in product_elem_list:
                product_link = await product_elem.get_attribute("href")
                if product_link:
                    product_urls.append({category_key: f"{self.url}{product_link}"})

        return product_urls

    async def get_product_details(self, page, product_urls: List[Dict[str, str]]):

        product_details = []
        product_image_urls = []
        async for i, product_url in tqdm(
            enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)

                    brand = "dior"

                    name = await page.locator(
                        "#main > div.ProductContent_container__i3zzp > div.ProductDetailsPanel_container__1QuVB > "
                        "div"
                        "> div > div.ProductDetailsPanel_content__MvVVv > div:nth-child(1) > "
                        "div.ProductDetailsHead_row-title__pZsRP > h1"
                    ).inner_text()

                    model = await page.locator(
                        "#main > div.ProductContent_container__i3zzp > div.ProductDetailsPanel_container__1QuVB > "
                        "div"
                        "> div > div.ProductDetailsPanel_content__MvVVv "
                        "div.ProductDetailsHead_row-subtitle__PeOd4 > span"
                    ).inner_text()
                    model = await convert_model(model)

                    origin_price_elem = page.locator(
                        "#main > div.ProductContent_container__i3zzp > "
                        "div.ProductDetailsPanel_container__1QuVB > div > div > "
                        "div.ProductDetailsPanel_content__MvVVv > "
                        "div.ProductActions_product-actions-container__uuL2o > button > span > span > div > "
                        "span.price-line"
                    )

                    if await origin_price_elem.is_visible():
                        origin_price = await origin_price_elem.inner_text()
                    else:
                        continue

                    origin_price = await convert_decimal(origin_price)

                    option_1 = await page.locator(
                        "#main > div.ProductContent_container__i3zzp > div.ProductDetailsPanel_container__1QuVB > "
                        "div"
                        "> div > div.ProductDetailsPanel_content__MvVVv > div:nth-child(1) > "
                        "div.ProductDetailsHead_row-subtitle__PeOd4 > div > h2"
                    ).inner_text()

                    image_url_elem = page.locator(
                        "#main > div.ProductContent_container__i3zzp > div.MediaGallery_container__vvOwI ul > "
                        "li:nth-child(1) img"
                    )

                    if await image_url_elem.is_visible():
                        image_url = await image_url_elem.get_attribute("src")
                    else:
                        image_url = ""

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": model.strip() if model else "",
                        "정가": origin_price,
                        "판매가": origin_price,
                        "옵션1": option_1.strip(),
                        "옵션2": "",
                        "링크": url.strip(),
                        "이미지소스": image_url.strip(),
                    }

                    product_details.append(product_detail_dict)
                    product_image_urls.append(image_url)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        category=category,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details, product_image_urls


class ScrapBottegaveneta(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="보테가베네타",
            url="https://www.bottegaveneta.com",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )

        self.categories = {
            "미니백": "/ko-kr/search?cgid=women-mini-bags",
            "크로스백": "/ko-kr/search?cgid=women-crossbody-bags",
            "숄더백": "/ko-kr/search?cgid=women-shoulder-bags",
            "탑핸들백": "/ko-kr/search?cgid=women-top-handle-bags",
            "토트백": "/ko-kr/search?cgid=women-tote-bags",
            "클러치": "/ko-kr/search?cgid=women-clutches",
            "트래블백": "/ko-kr/search?cgid=women-travel-bag",
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:
        await self.click_on_cookie_button(
            page=page, selector="#onetrust-accept-btn-handler", sleep=1
        )

        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_DETAILS_DES
        ):
            await page.goto(f"{self.url}{category_value}")
            await self.scroll_to_the_bottom(page=page, interval=500, sleep=1)

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "div.c-product__wrapper > a.c-product__link"
            ).all()

            for product_elem in product_elem_list:
                product_link = await product_elem.get_attribute("href")
                product_urls.append({category_key: f"{self.url}{product_link}"})

        return product_urls

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[str]]:

        product_details = []
        product_image_urls = []
        async for i, product_url in tqdm(
            iterable=enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)

                    brand = "bottegaveneta"
                    name = await page.locator(
                        "#main-content > div.l-pdp > div:nth-child(8) > div > div.l-pdp__productinfos > div.c-product >"
                        "div > h1"
                    ).inner_text()

                    model = await page.locator(
                        "#productLongDescContainer > div > p.c-product__id > span"
                    ).inner_text()
                    model = await convert_model(model)

                    origin_price = await page.locator(
                        "#main-content > div.l-pdp > div:nth-child(8) > div > "
                        "div.l-pdp__productinfos > div.c-product > div > div.l-pdp__prices "
                        "> div > p"
                    ).inner_text()
                    origin_price = await convert_decimal(origin_price)
                    sale_price = origin_price

                    option_1 = await page.locator(
                        "#main-content > div.l-pdp > div:nth-child(8) > div > "
                        "div.l-pdp__productinfos > div.c-product > div > div:nth-child("
                        "5)"
                    ).inner_text()

                    option_elem_button = page.locator(
                        "#otherVariations > div:nth-child(1) > button"
                    )
                    option_2 = ""
                    if await option_elem_button.is_visible():
                        options = []

                        await asyncio.sleep(1)
                        await page.wait_for_load_state()
                        option_elem_list = await page.locator(
                            "ul.c-productvariationcarousel__wrapper > li span.c-otherproductvariationscarousel__modellabel"
                        ).all()

                        for option_elem in option_elem_list:
                            option = await option_elem.inner_text()
                            options.append(option.strip())

                        option_join = ", ".join(options)
                        option_2 = f"사이즈: {option_join}"

                    image_url = await page.locator(
                        "#slider-images-product > div > div > div.c-productcarousel > ul > "
                        "li:nth-child(1) > button > img"
                    ).get_attribute("src")

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": model.strip(),
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": option_1.strip(),
                        "옵션2": option_2.strip(),
                        "링크": url.strip(),
                        "이미지소스": image_url.strip(),
                    }

                    product_details.append(product_detail_dict)
                    product_image_urls.append(image_url)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        category=category,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details, product_image_urls


class ScrapSaintLaurent(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="생로랑",
            url="https://www.ysl.com",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )

        self.categories = {
            "크로스바디 백": "/ko-kr/여성-쇼핑/핸드백/크로스바디-백",
            "숄더 백": "/ko-kr/여성-쇼핑/핸드백/숄더-백",
            "탑 핸들백": "/ko-kr/여성-쇼핑/핸드백/탑-핸들백",
            "맥시 백": "/ko-kr/여성-쇼핑/핸드백/맥시-백",
            "미니백": "/ko-kr/여성-쇼핑/핸드백/미니백",
            "사첼 또는 버킷백": "/ko-kr/여성-쇼핑/핸드백/사첼-또는-버킷백",
            "토드백": "/ko-kr/여성-쇼핑/핸드백/토트백",
            "클리치 및 이브닝": "/ko-kr/여성-쇼핑/핸드백/클러치",
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:
        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")
            await self.scroll_to_the_bottom(page=page, interval=1000, sleep=1)

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "ul.c-productcarousel__wrapper > li.c-productcarousel__slide.swiper-slide-active > a"
            ).all()

            for product_elem in product_elem_list:
                product_link = await product_elem.get_attribute("href")
                product_urls.append({category_key: f"{self.url}{product_link}"})

        return product_urls

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[str]]:

        product_details = []
        product_image_urls = []
        async for i, product_url in tqdm(
            iterable=enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)

                    brand = "saint laurent"
                    name = await page.locator(
                        "#main-content > div > div > div:nth-child(10) > div > "
                        "div.l-pdp__productinfos > div > div > div.c-productinfos > div.c-product >"
                        " h1"
                    ).inner_text()
                    model = await page.locator(
                        "#productLongDesc > div > ul > li:nth-child(3) > span"
                    ).inner_text()

                    origin_price = await page.locator(
                        "#main-content > div > div > div:nth-child(10) > div > "
                        "div.l-pdp__productinfos > div > div > div.c-productinfos > "
                        "div.c-product > div.l-pdp__prices > div > div > p"
                    ).inner_text()
                    origin_price = await convert_decimal(origin_price)
                    sale_price = origin_price

                    image_url = await page.locator(
                        "#slider-images-product > div > div.c-productcarousel > ul > "
                        "li:nth-child(1) > button > span > img"
                    ).get_attribute("src")

                    option_label_1 = await page.locator(
                        "#title-color-variation"
                    ).inner_text()
                    option_1 = await page.locator(
                        "#main-content > div > div > div:nth-child(10) > div > "
                        "div.l-pdp__productinfos > div > div > div.c-productinfos > "
                        "div.c-product > div.l-pdp__variants > div > div:nth-child(1) > div > "
                        "p"
                    ).inner_text()
                    option_1 = f"{option_label_1} {option_1}"

                    option_elem_area2 = page.locator(
                        "div.c-product__othervariationsbuttoncontainer"
                    )
                    option_2 = ""
                    if await option_elem_area2.is_visible():
                        await option_elem_area2.click()

                        option_label_2 = await option_elem_area2.locator(
                            "h2.c-product__sizeaccordionlabel"
                        ).inner_text()
                        options = []

                        await asyncio.sleep(1)
                        await page.wait_for_load_state()

                        option_elem_list = await page.locator(
                            "span.c-otherproductvariationscarousel__modellabel"
                        ).all()

                        for option_elem in option_elem_list:
                            option = await option_elem.inner_text()
                            options.append(f"{option_label_2} {option.strip()}")

                        option_2 = ", ".join(options)

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": model.strip(),
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": option_1.strip(),
                        "옵션2": option_2.strip(),
                        "링크": url.strip(),
                        "이미지소스": image_url.strip(),
                    }

                    product_details.append(product_detail_dict)
                    product_image_urls.append(image_url)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        category=category,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details, product_image_urls


class ScrapBalenciaga(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="발렌시아가",
            url="https://www.balenciaga.com",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )

        self.categories = {
            "핸드백": "/ko-kr/여성/가방/핸드백",
            "숄더백": "/ko-kr/여성/가방/숄더백",
            "미니백": "/ko-kr/여성/가방/미니백",
            "체인백": "/ko-kr/여성/가방/체인백",
            "토드백": "/ko-kr/여성/가방/토트백",
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:

        await self.click_on_cookie_button(
            page=page, selector="#onetrust-accept-btn-handler", sleep=1
        )

        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")

            await asyncio.sleep(1)
            await self.scroll_to_the_bottom(page=page, interval=1000, sleep=1.5)

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "#product-search-results > div.l-productgrid__wrapper > ul > li > "
                "article > div > a"
            ).all()

            for i, product_elem in enumerate(product_elem_list):
                product_link = await product_elem.get_attribute("href")
                product_urls.append({category_key: f"{self.url}{product_link}"})

                sold_out_elem = product_elem.locator(
                    "div.c-product__generictag > div.c-product__availability"
                )

                if await sold_out_elem.is_visible():
                    sold_out = await sold_out_elem.inner_text()

                    if "품절" in sold_out or "재입고" in sold_out:
                        await self.setup_product_error_log(
                            page=page,
                            category=category_key,
                            url=product_link,
                            product_no=self.init_product_no + i,
                            message="품절 상품 제외",
                            availability_screenshot=False,
                        )
                    continue

        return product_urls

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[str]]:
        product_details = []
        product_image_urls = []
        async for i, product_url in tqdm(
            iterable=enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)

                    brand = "balenciaga"
                    name = await page.locator(
                        "#main-content > div > div:nth-child(13) > div > div.l-pdp__watermark > "
                        "div.l-pdp__productinfos > div > header > div.l-pdp__productname > "
                        "h1"
                    ).inner_text()

                    await page.locator(
                        r"#productShipping > div.c-accordion__section.\.c-productdetails > h2 > button"
                    ).click()
                    model_elem = page.locator(
                        "#accordionPanelDetails > div > div.c-product__id > span"
                    )
                    await model_elem.scroll_into_view_if_needed()
                    model = await model_elem.inner_text()
                    model = await convert_model(model)

                    origin_price = await page.locator(
                        "#main-content > div > div:nth-child(13) > div > div.l-pdp__watermark > "
                        "div.l-pdp__productinfos > div > header > div.l-pdp__productname > div.l-pdp__prices > div > p"
                    ).inner_text()
                    origin_price = await convert_decimal(origin_price)
                    sale_price = origin_price

                    option_1 = ""
                    option_2 = ""

                    await asyncio.sleep(1)
                    image_url = await page.locator(
                        "#slider-images-product > div > div.c-productcarousel > ul > li:nth-child(1) > button > img"
                    ).get_attribute("src")

                    if not image_url.startswith("https://balenciaga.dam.kering.com/"):
                        await self.setup_product_error_log(
                            page=page,
                            url=url,
                            product_no=self.init_product_no + i,
                            message="상품 상세 페이지 이미지 로드 실패",
                        )

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": model.strip(),
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": option_1.strip(),
                        "옵션2": option_2.strip(),
                        "링크": url.strip(),
                        "이미지소스": image_url.strip(),
                    }

                    product_details.append(product_detail_dict)
                    product_image_urls.append(image_url)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        category=category,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )
        return product_details, product_image_urls


# 명품 끝


# 종합 시작
class ScrapGiftKakao(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="카카오",
            url="https://gift.kakao.com",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )

        self.categories = {
            # delivery_categories
            "식품": "/ranking/best/delivery/4",
            "화장품/향수": "/ranking/best/delivery/2",
            "패션": "/ranking/best/delivery/1",
            "리빙": "/ranking/best/delivery/5",
            "건강": "/ranking/best/delivery/8",
            "카카오프렌즈": "/ranking/best/delivery/11",
            "명품패션": "/ranking/best/delivery/9",
            "가전/디지털": "/ranking/best/delivery/7",
            "꽃배달": "/ranking/best/delivery/10",
            "레저/스포츠": "/ranking/best/delivery/6",
            "출산/유아동": "/ranking/best/delivery/3",
            "도서/음반": "/ranking/best/delivery/21",
            "반려동물": "/ranking/best/delivery/20",
            # coupon_categories
            "카페": "/ranking/best/coupon/14",
            "베이커리/떡": "/ranking/best/coupon/13",
            "버거/치킨/피자": "/ranking/best/coupon/16",
            "아이스크림/도넛": "/ranking/best/coupon/15",
            "외식": "/ranking/best/coupon/17",
            "상품권/마트": "/ranking/best/coupon/12",
            "생활편의/기타": "/ranking/best/coupon/19",
            "영화/테마파크/전시": "/ranking/best/coupon/18",
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:

        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")
            await asyncio.sleep(1)
            await self.scroll_to_the_bottom(page=page, interval=1500, sleep=1)

            await page.wait_for_load_state()
            product_elem_list = await page.locator("div.thumb_prd > gc-link > a").all()

            for i, product_elem in enumerate(product_elem_list):
                check_for_elem = product_elem.locator(
                    "product-stamp > span > span.minor_badge > em"
                )

                product_link = await product_elem.get_attribute("href")

                # 19세 이상, 품절 상품 제외
                if await check_for_elem.is_visible():
                    state_text = await check_for_elem.inner_text()
                    if "19세" in state_text:
                        await self.setup_product_error_log(
                            page=page,
                            category=category_key,
                            url=product_link,
                            product_no=self.init_product_no + i,
                            message="19세 상품 제외",
                            availability_screenshot=False,
                        )
                        continue

                    if "SOLD OUT" in state_text:
                        await self.setup_product_error_log(
                            page=page,
                            category=category_key,
                            url=product_link,
                            product_no=self.init_product_no + i,
                            message="품절 상품 제외",
                            availability_screenshot=False,
                        )
                        continue

                product_urls.append({category_key: f"{self.url}{product_link}"})

        return product_urls

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[str]]:

        product_details = []
        product_image_urls = []
        async for i, product_url in tqdm(
            iterable=enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)

                    brand = await page.locator(
                        "#mArticle > app-home > div > app-main > div > div > div.wrap_basic_info > div "
                        "> div.wrap_brand > gc-link > a > div > span.txt_shopname"
                    ).inner_text()

                    name = await page.locator(
                        "#mArticle > app-home > div > app-main > div > div > div.wrap_basic_info > div > "
                        "div.product_subject"
                        "> h2"
                    ).inner_text()

                    origin_price_elem = page.locator(
                        "#mArticle > app-home > div > app-main > div > div > div.wrap_basic_info > div > "
                        "div.info_product.clear_g > div.wrap_priceinfo.clear_g > span.txt_total"
                    )

                    sale_price_elem = page.locator(
                        "#mArticle > app-home > div > app-main > div > div > div.wrap_basic_info > div > "
                        "div.info_product.clear_g > div.wrap_priceinfo.clear_g > span.txt_price > del"
                    )

                    origin_price, sale_price = await self.price_position_conversion(
                        origin_price_elem, sale_price_elem
                    )

                    image_selector = (
                        "#mArticle > app-home > div > app-main > div > div > div.warp_thumb_product > div > "
                        "cu-carousel > swiper-container > swiper-slide.cont_slide.swiper-slide-active > img"
                    )
                    await page.wait_for_function(
                        f"""
                        () => {{
                            const img = document.querySelector("{image_selector}");
                            return img.complete && img.naturalHeight !== 0;
                        }}
                        """
                    )
                    image_url = await page.locator(image_selector).first.get_attribute(
                        "src"
                    )

                    if not image_url.startswith("https://img1"):
                        await self.setup_product_error_log(
                            page=page,
                            url=url,
                            product_no=self.init_product_no + i,
                            message="상품 상세 페이지 이미지 로드 실패",
                        )

                    option_name_elem = page.locator(
                        "#buyInfo > app-product-option > app-bottom-layer > div > div > app-options > "
                        "div.wrap_option.fst.option_on > button > strong > span"
                    )

                    # 옵션 & 모델 존재 여부 체크
                    option_1 = None
                    model = None
                    if await option_name_elem.is_visible():
                        option_name = await option_name_elem.inner_text()

                        await page.wait_for_load_state()
                        option_elem_list = await page.locator(
                            "#buyInfo > app-product-option > app-bottom-layer > div > div > app-options > div > ul > li"
                        ).all()

                        option_list1 = []
                        for option_elem in option_elem_list:
                            option = await option_elem.locator("label").inner_text()

                            # 품절 상태 확인
                            check_for_option = option_elem.locator("span.txt_soldout")
                            if await check_for_option.is_visible():
                                sold_out = await check_for_option.inner_text()
                                option = f"{option.strip()} ({sold_out.strip()})"

                            option_list1.append(option)

                            # 모델명
                            if option_name == "모델명":
                                model = re.sub(r"\s*\([^)]*\)\s*", "", option)

                        option_1 = ", ".join(option_list1)
                    else:
                        option_name = None

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": model.strip() if model else "",
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": (
                            f"{option_name.strip()}: {option_1.strip()}"
                            if option_name and option_1
                            else ""
                        ),
                        "옵션2": "",
                        "링크": url.strip(),
                        "이미지소스": image_url.strip(),
                    }

                    product_details.append(product_detail_dict)
                    product_image_urls.append(image_url)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        category=category,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details, product_image_urls


class ScrapNaverBrandStore(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="네이버",
            url="https://brand.naver.com",
            root_category="디지털/가전",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )

        self.categories = {
            "샤오미": "/xiaomi/best?cp=1",
            "티피링크": "/tplink/category/125eb5683c1e4c90b742220ead9d265a?st=POPULAR&dt=IMAGE&page=1&size=80",
            "앤커": "/anker/best?cp=1",
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:

        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "#CategoryProducts > ul > li > div > a"
            ).all()

            for product_elem in product_elem_list:
                product_link = await product_elem.get_attribute("href")
                product_urls.append({category_key: f"{self.url}{product_link}"})

        return product_urls

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[str]]:

        product_details = []
        product_image_urls = []
        async for i, data in tqdm(
            enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for sub_site_name, url in data.items():
                try:
                    await page.goto(url)

                    await page.wait_for_load_state()
                    await page.locator(
                        "#INTRODUCE > div > div.attribute_wrapper > div"
                    ).scroll_into_view_if_needed()

                    brand_elem = page.locator(
                        '//th[text()="브랜드"]/following-sibling::td'
                    )

                    brand = ""
                    if await brand_elem.is_visible():
                        brand = await brand_elem.inner_text()
                        brand = brand.strip().replace("ANKER", "앤커")

                    name = await page.locator(
                        "#content > div > div._2-I30XS1lA > div._2QCa6wHHPy > fieldset > div._3k440DUKzy > "
                        "div._1eddO7u4UC > h3"
                    ).inner_text()

                    model_elem = page.locator(
                        '//th[text()="모델명"]/following-sibling::td'
                    ).first

                    model = ""
                    if await model_elem.is_visible():
                        model = await model_elem.inner_text()

                    if re.search(r"[가-힣]", model):
                        model = ""

                    origin_price_elem = page.locator(
                        "#content > div > div._2-I30XS1lA > div._2QCa6wHHPy > fieldset > div._3k440DUKzy > "
                        "div.WrkQhIlUY0 >"
                        "div > strong > span._1LY7DqCnwR"
                    )
                    sale_price_elem = page.locator(
                        "#content > div > div._2-I30XS1lA > div._2QCa6wHHPy > fieldset > "
                        "div._3k440DUKzy > div.WrkQhIlUY0 > div > del > span._1LY7DqCnwR"
                    )

                    origin_price, sale_price = await self.price_position_conversion(
                        origin_price_elem, sale_price_elem
                    )

                    option_elem_1 = page.locator(
                        "#content > div > div._2-I30XS1lA > div._2QCa6wHHPy > fieldset > div.bd_2dy3Y > "
                        "div:nth-child(1)"
                    )
                    option_elem_2 = page.locator(
                        "#content > div > div._2-I30XS1lA > div._2QCa6wHHPy > fieldset > div.bd_2dy3Y > "
                        "div:nth-child(2)"
                    )

                    option_1, option_2 = await self.get_options(
                        page, option_elem_1=option_elem_1, option_elem_2=option_elem_2
                    )

                    image_url = await page.locator(
                        "#content > div > div._2-I30XS1lA > div._3rXou9cfw2 > div > div img"
                    ).first.get_attribute("src")

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": self.root_category,
                        "브랜드": brand.strip() if brand else sub_site_name,
                        "상품명": name.strip(),
                        "모델명": model.strip(),
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": option_1.strip(),
                        "옵션2": option_2.strip(),
                        "링크": url.strip(),
                        "이미지소스": image_url.strip(),
                    }

                    product_details.append(product_detail_dict)
                    product_image_urls.append(image_url)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        category=sub_site_name,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details, product_image_urls

    @classmethod
    async def get_options(
        cls, page: Page, option_elem_1: Locator, option_elem_2: Locator
    ):
        async def get_option_names(option_elem: Locator):
            if await option_elem.is_visible():
                option_root_name = await option_elem.inner_text()
                await option_elem.get_by_role("button").click()

                await page.wait_for_load_state()
                option_child_elem_list = await option_elem.locator("ul > li").all()

                option_child_names = []
                for option_child_elem in option_child_elem_list:
                    option_child_name = await option_child_elem.inner_text()

                    if "품절" in option_child_name:
                        continue

                    option_child_names.append(option_child_name.strip())

                option_child_name = ", ".join(option_child_names)
                await option_child_elem_list[0].get_by_role("option").click()

                return f"{option_root_name.strip()}: {option_child_name}"

        options_1 = await get_option_names(option_elem_1)
        options_2 = await get_option_names(option_elem_2)

        return options_1 if options_1 else "", options_2 if options_2 else ""


class ScrapHM(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="H & M",
            url="https://www2.hm.com",
            root_category="패션/잡화",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )
        self.categories = {"Women": "/ko_kr/ladies/new-arrivals/view-all.html"}

    async def create(self) -> Tuple[List[dict], List[str]]:
        async with async_playwright() as p:
            try:
                browser, page = await self.setup_playwright(p)
                await page.goto(self.url)

                product_urls, product_image_urls = await self.get_product_urls(
                    page=page
                )

                product_details = await self.get_product_details(
                    page=page, product_urls=product_urls
                )

                for product_detail, product_image_url in zip(
                    product_details, product_image_urls
                ):
                    product_detail["이미지소스"] = product_image_url

            finally:
                await page.close()
                await browser.close()

        return product_details, product_image_urls

    async def get_product_urls(self, page: Page) -> Tuple[List[Dict], List[str]]:

        await self.click_on_cookie_button(
            page=page, selector="#onetrust-accept-btn-handler", sleep=1
        )

        product_urls = []
        product_image_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")

            await self.click_on_load_more_button(
                page=page,
                selector="#page-content > div > div > div.load-more-products > button",
                sleep=2,
            )

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "#page-content > div > div > ul > li > article > div.image-container"
            ).all()

            for product_elem in product_elem_list:
                await product_elem.scroll_into_view_if_needed()
                await asyncio.sleep(0.2)
                await product_elem.hover()

                product_link = await product_elem.locator("a").get_attribute("href")

                product_image = await product_elem.locator("img").get_attribute("src")
                product_image = urllib.parse.urljoin("https:", product_image)

                product_urls.append({category_key: f"{self.url}{product_link}"})
                product_image_urls.append(product_image)

            print(product_urls)

        return product_urls, product_image_urls

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> List[dict]:

        product_details = []
        async for i, product_url in tqdm(
            iterable=enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)

                    brand = self.site_name
                    name = await page.locator(
                        "#js-product-name > div > h1"
                    ).inner_text()

                    origin_price_elem = page.locator("#product-price > div > .d9ca8b")
                    origin_price = await origin_price_elem.inner_text()
                    origin_price = await convert_decimal(origin_price)
                    sale_price = origin_price

                    option_1 = await page.locator(
                        "#main-content > div.product.parbase > "
                        "div.layout.pdp-wrapper.product-detail.sticky-footer-wrapper.js-reviews > "
                        "div.module.product-description.sticky-wrapper.pdp-container > div.column2 > "
                        "div > div > div.product-colors.miniatures.clearfix.slider-completed.loaded > "
                        "h3"
                    ).inner_text()
                    option_1 = f"색상: {option_1.strip()}"
                    option_2 = ""
                    option_area = page.locator("div.product-item-buttons.BOSS")
                    option_label_elem = option_area.locator(
                        "#size-selector > div > span"
                    )
                    if await option_label_elem.is_visible():
                        option_label = await option_label_elem.inner_text()

                        await page.wait_for_load_state()
                        option_elem_list = await option_area.locator(
                            "#size-selector > ul > li"
                        ).all()

                        options = []
                        for option_elem in option_elem_list:
                            if await option_elem.locator("div").is_disabled():
                                continue

                            option = await option_elem.locator(
                                "div > label"
                            ).inner_text()
                            option = option.strip().replace("재고가 거의 없습니다.", "")
                            options.append(f"{option_label.strip()}: {option.strip()}")

                        option_2 = ", ".join(options)

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": self.root_category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": "",
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": option_1.strip(),
                        "옵션2": option_2.strip(),
                        "링크": url.strip(),
                    }
                    product_details.append(product_detail_dict)
                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details


class ScrapZARA(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="ZARA",
            url="https://www.zara.com",
            root_category="패션/잡화",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )
        self.categories = {
            "woman": "/kr/ko/woman-must-have-l4108.html?v1=2352612&page=2"
        }

    async def get_product_urls(self, page: Page) -> List[Dict[str, str]]:

        await self.click_on_cookie_button(
            page=page, selector="#onetrust-accept-btn-handler", sleep=1
        )

        product_urls = []
        async for category_key, category_value in tqdm(
            iterable=self.categories.items(), desc=self.PRODUCT_URLS_DES
        ):
            await page.goto(f"{self.url}{category_value}")

            await self.scroll_to_the_bottom(page=page, interval=1000, sleep=1)

            await page.wait_for_load_state()
            product_elem_list = await page.locator(
                "#main > article > div.product-groups > section > ul > li > "
                "div.product-grid-product__figure > a"
            ).all()

            for product_elem in product_elem_list:
                product_link = await product_elem.get_attribute("href")
                product_urls.append({category_key: f"{product_link}"})

        return product_urls

    async def get_product_details(
        self, page: Page, product_urls: List[Dict[str, str]]
    ) -> Tuple[List[dict], List[List[str]]]:

        product_details = []
        product_image_urls = []
        async for i, product_url in tqdm(
            iterable=enumerate(product_urls),
            total=len(product_urls),
            desc=self.PRODUCT_DETAILS_DES,
        ):
            for category, url in product_url.items():
                try:
                    await page.goto(url)

                    brand = self.site_name
                    name = await page.locator(
                        "#main > article > div > div.product-detail-view__main > "
                        "div.product-detail-view__side-bar > div > div.product-detail-info__info > "
                        "div.product-detail-info__header > div > h1"
                    ).inner_text()
                    origin_price = await page.locator(
                        "#main > article > div.product-detail-view__content > "
                        "div.product-detail-view__main > div.product-detail-view__side-bar > "
                        "div > div.product-detail-info__info > div.product-detail-info__price > "
                        "div > span > span > span > div > span"
                    ).inner_text()
                    origin_price = await convert_decimal(origin_price)
                    sale_price = origin_price

                    option_1 = await page.locator(
                        "div.product-detail-info__actions p"
                    ).inner_text()
                    option_1 = f"색상: {await convert_string(option_1)}".replace(
                        "컬러", ""
                    )

                    await page.wait_for_load_state()
                    option_elem_list = await page.locator(
                        "ul.size-selector-list > li.size-selector-list__item"
                    ).all()

                    options = []
                    for option_elem in option_elem_list:
                        sold_out = await option_elem.get_attribute("class")

                        if "size-selector-list__item--is-disabled" in sold_out:
                            continue

                        option = await option_elem.locator(
                            "div.product-size-info__size > div.product-size-info__main-label"
                        ).inner_text()
                        options.append(f"사이즈: {option.strip()}")

                    option_2 = ", ".join(options)

                    await page.wait_for_load_state()
                    image_elem_list = await page.locator(
                        "#main > article > div.product-detail-view__content > div.product-detail-view__main > "
                        "div.product-detail-view__main-content > section > div.product-detail-images__frame > ul > "
                        "li > button > div > div > picture > img"
                    ).all()

                    image_urls = []
                    for image_elem in image_elem_list:
                        await image_elem.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                        image_url = await image_elem.get_attribute("src")
                        image_urls.append(image_url)

                        if image_url.startswith(
                            "https://static.zara.net/stdstatic/6.11.0/images/transparent"
                            "-background.png"
                        ):
                            logger = await get_logger()
                            logger.error(
                                f"'{self.init_product_no + i}' 번째 '{self.site_name}' 이미지를 불러오는 중에 오류가 발생했습니다."
                            )

                    product_image_urls.append(image_urls)
                    image_url = ";\n".join(image_urls)

                    product_detail_dict = {
                        "상품번호": self.init_product_no + i,
                        "사이트": self.site_name,
                        "카테고리": self.root_category,
                        "브랜드": brand.strip(),
                        "상품명": name.strip(),
                        "모델명": "",
                        "정가": origin_price,
                        "판매가": sale_price,
                        "옵션1": option_1.strip(),
                        "옵션2": option_2.strip() if option_2 else "",
                        "링크": url.strip(),
                        "이미지소스": image_url.strip(),
                    }
                    product_details.append(product_detail_dict)

                except Exception as e:
                    await self.setup_product_error_log(
                        page=page,
                        url=url,
                        product_no=self.init_product_no + i,
                        message="상품 상세 페이지 에러 발생",
                    )

        return product_details, product_image_urls


# 종합 끝


# 리뷰 시작
class ScrapGooglePlayReView(ScrapUtil):
    def __init__(self, init_product_no: int = 1):
        super().__init__(
            site_name="구글 플레이",
            url="https://play.google.com/store",
            root_dirname="구글 플레이 리뷰",
            root_category="리뷰",
            headless=False,
            timeout=30000,
            init_product_no=init_product_no,
        )
        self.categories = {
            "럭키탕": "/apps/details?id=com.didimstory.luckyTang",
            "해시박스": "/apps/details?id=monster.didimstory.hashbox&hl=ko",
            "우주마켓": "/apps/details?id=com.shop.uzumarket&hl=ko",
            "랜덤팡": "/apps/details?id=com.shop.randompang&hl=ko",
            "포켓팡팡": "/apps/details?id=com.pocketpangpang.pocketpangpang",
            "트랜덤": "/apps/details?id=com.trandom&hl=ko",
            "윈트박스": "/apps/details?id=com.onest.wonbox&hl=ko",
            "굿럭박스": "/apps/details?id=com.goodluckbox.flutter_goodluckbox&hl=ko",
            "가자박스": "/apps/details?id=com.gazakorea.gazabox_01&hl=ko",
            "랜덤마트": "/apps/details?id=kr.co.RandomMart&hl=ko",
            "보물선": "/apps/details?id=com.store5000",
            "캐치유": "/apps/details?id=com.KLP.RZG",
            "산타의연못": "/apps/details?id=com.smtnt.santapond&hl=ko",
        }

    async def create(self) -> None:
        async with async_playwright() as p:
            try:
                browser, page = await self.setup_playwright(p)
                await page.goto(self.url)
                await self.get_review_details(page)

            finally:
                await page.close()
                await browser.close()

    async def get_review_details(self, page: Page) -> None:
        for key, url in self.categories.items():
            url = f"{self.url}{url}"
            try:
                await page.goto(url)

                # not modal start
                appname = await page.locator("div.hnnXjf > div > div > h1").inner_text()

                appname_match = re.match(r"^[^\s-]+", appname)
                appname = appname_match.group()

                total_rating = await page.locator("div.jILTFe").inner_text()
                total_rating = float(total_rating.strip())

                total_review = (
                    await page.locator(
                        "div.JU1wdd > div.l8YSdd > div.w7Iutd > div.wVqUob"
                    )
                    .first.locator("div.g1rdde")
                    .inner_text()
                )
                total_review = re.sub("[^0-9.]", "", total_review)
                if "." in total_review:
                    total_review = float(total_review.strip())
                    total_review = int(total_review * 1000)
                else:
                    total_review = await convert_decimal(total_review)

                review_model_button = page.locator(
                    "#yDmH0d > c-wiz.SSPGKf.Czez9d > div > div > div:nth-child(1) > div > div.wkMJlb.YWi3ub > div > "
                    "div.qZmL0 > div:nth-child(1) > c-wiz:nth-child(4) > section > div > div.Jwxk6d > div:nth-child("
                    "5) >"
                    "div > div > button"
                )
                await review_model_button.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                await review_model_button.click()
                await asyncio.sleep(1)
                # not modal end

                # modal start
                review_modal_area = page.locator(
                    "#yDmH0d > div.VfPpkd-Sx9Kwc.cC1eCc.UDxLd.PzCPDd.HQdjr.VfPpkd-Sx9Kwc-OWXEXe-FNFY6c > "
                    "div.VfPpkd-wzTsW"
                    "> div"
                )

                transform_buttons = []
                menu_toggle = page.locator('//*[@id="formFactor_2"]/div[2]/i')
                if await menu_toggle.is_visible():
                    phone = review_modal_area.locator("div.jO7h3c").get_by_text("전화")
                    tablet = review_modal_area.locator("div.jO7h3c").get_by_text(
                        "태블릿"
                    )
                    transform_buttons.append(phone)
                    transform_buttons.append(tablet)
                else:
                    phone = review_modal_area.locator(
                        "#formFactor_2 > div.kW9Bj"
                    ).get_by_text("전화")
                    transform_buttons.append(phone)

                total_review_result = 0
                review_details = []
                for transform_button in transform_buttons:

                    if await menu_toggle.is_visible():
                        await menu_toggle.scroll_into_view_if_needed()
                        await asyncio.sleep(1)
                        await menu_toggle.click()
                        await asyncio.sleep(1)

                    distinction = await transform_button.inner_text()

                    total_range = int(total_review) // 4
                    current_range = (
                        total_range if distinction == "전화" else total_range // 4
                    )

                    await transform_button.click()

                    if await review_modal_area.is_visible():
                        modal_box = await review_modal_area.bounding_box()
                        modal_box_pos_x = modal_box["x"] + modal_box["width"] / 2
                        modal_box_pos_y = modal_box["y"] + modal_box["height"] / 2
                        await page.mouse.move(modal_box_pos_x, modal_box_pos_y)

                        for _ in tqdm(
                            iterable=range(current_range),
                            desc=f"{appname} {distinction} 리뷰 스크롤 진행 중",
                        ):
                            await page.mouse.wheel(0, 4000)
                            await asyncio.sleep(0.1)

                        await page.wait_for_load_state()
                        review_elem_list = await review_modal_area.locator(
                            "div.RHo1pe"
                        ).all()

                        current_review_result = len(review_elem_list)
                        total_review_result += current_review_result

                        for review_elem in tqdm(
                            iterable=review_elem_list,
                            desc=f"{appname} {distinction} 리뷰 스크랩 진행 중",
                        ):
                            # user start
                            user_nickname = await review_elem.locator(
                                "div.X5PpBb"
                            ).inner_text()
                            user_inquiry_date = await review_elem.locator(
                                "span.bp9Aid"
                            ).inner_text()
                            user_content = await review_elem.locator(
                                "div.h3YV2d"
                            ).inner_text()
                            user_rating = (
                                await review_elem.locator("div.Jx4nYe")
                                .get_by_role("img")
                                .get_attribute("aria-label")
                            )
                            user_rating = user_rating
                            user_like_elem = review_elem.locator("div.AJTPZc")
                            user_like = ""
                            if await user_like_elem.is_visible():
                                user_like = await user_like_elem.inner_text()
                                user_like = await convert_decimal(user_like)

                            user_like_match = re.search(
                                r"\d+개 만점에 (\d+)개", user_rating
                            )
                            if user_like_match:
                                second_number = user_like_match.group(1)
                                user_rating = second_number
                            # user end

                            # answer start
                            answer_area = review_elem.locator("div.ocpBU")
                            answer_content = ""
                            answer_date = ""
                            if await answer_area.is_visible():
                                answer_date = await answer_area.locator(
                                    "div.I9Jtec"
                                ).inner_text()
                                answer_content = await answer_area.locator(
                                    "div.ras4vb > div"
                                ).inner_text()

                            review_detail_dict = {
                                "사이트": self.site_name,
                                "분류": distinction.strip(),
                                "어플명": appname.strip(),
                                "총 평점": total_rating,
                                "총 리뷰 건수": total_review,
                                "총 실제 리뷰 건수": total_review_result,
                                "문의 일자": user_inquiry_date.strip(),
                                "답변 일자": answer_date.strip(),
                                "닉네임": user_nickname.strip(),
                                "평점": int(user_rating),
                                "좋아요": user_like,
                                "내용": user_content.strip(),
                                "답변 내용": answer_content.strip(),
                            }
                            review_details.append(review_detail_dict)
                            # answer end
                # modal end

                for review_detail in review_details:
                    review_detail["총 실제 리뷰 건수"] = total_review_result

                excel_file = await create_xlsx_file(
                    data=review_details,
                    file_name=appname,
                    sheet_name=self.root_category,
                )

                tasks = [
                    save_to_xlsx(
                        xlsx_file=excel_file,
                        dirname=self.root_dirname,
                    ),
                ]

                await asyncio.gather(*tasks)

            except Exception as e:
                await self.setup_product_error_log(
                    page=page,
                    url=url,
                    product_no=1,
                    message="상품 상세 페이지 에러 발생",
                )


# 리뷰 끝
