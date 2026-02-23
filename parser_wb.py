import queue

from selenium import webdriver
from selenium_stealth import stealth
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

import re
import json
import requests
import pandas as pd
from lxml import html


class SeleniumUtility:
    def __init__(self):
        # url
        self.wb_url = 'https://www.wildberries.ru'
        self.categories_url = 'https://static-basket-01.wbbasket.ru/vol0/data/main-menu-ru-ru-v2.json'

    def get_driver(self):
        # driver settings
        driver = webdriver.Chrome()
        stealth(driver, platform='wind32')
        return driver

    def build_json_with_categories(self) -> None:
        """Берёт информацию из внешнего json, убирает лишние категории и строит свой json с вложенностями с помощью функции
        self.build_dict"""
        result = {}
        trash_categories = ('Культурный код', 'Цифровые товары', 'Путешествия',
                            'распроДАДАДАжа', 'Сертификаты Wildberries', 'Акции',
                            'Цифровые книги', 'Цифровые аудиокниги', 'Школа')

        response = requests.get(self.categories_url)
        categories = (category for category in json.loads(response.text) if category['name'] not in trash_categories)

        with open('categories.json', 'w', encoding='utf-8') as file:
            for category in categories:
                self.build_dict(result, category)
            json.dump(result, file, indent=4, ensure_ascii=False)

    def build_dict(self, level: dict, category: dict) -> None:
        """Рекурсивно выстраивает dict для работы"""
        entity = category.get('childs', category.get('url'))

        if type(entity) is list:
            for child in entity:
                level.setdefault(category.get('name'), {})
                self.build_dict(level[category.get('name')], child)
        else:
            level.setdefault(category.get('name'), entity)

    def parse(self, url: str, driver: webdriver, elements_limit: int = 70) -> list:
        """Выполняет парсинг страницы до определённого лимита или прекращения появления новых элементов на странице"""
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'catalog-page__content')))
        # Переменные для цикла
        last_cards_len = 0
        current_card_len = 0
        self.attempts_count = 0

        while True and self.attempts(last_cards_len, current_card_len):
            last_cards_len = len(self.get_cards(driver.page_source))
            driver.execute_script('window.scrollBy(0, document.body.scrollHeight)')
            current_card_len = len(self.get_cards(driver.page_source))
            if current_card_len >= elements_limit:
                break
            driver.execute_script('window.scrollBy(0, -200)')

        all_goods_card = self.get_cards(driver.page_source)[:elements_limit]
        return all_goods_card

    def attempts(self, last_cards_len: int, current_card_len: int) -> bool:
        """Используется функцией self.parce() для выявления тупиковой ситуации - когда новые элементы не появляются,
        парсинг прекращается"""
        if last_cards_len == current_card_len:
            self.attempts_count += 1
        else:
            self.attempts_count = 0
        print(self.attempts_count)
        if self.attempts_count == 10:
            return False
        return True

    def extract_data_from_html(self, cards: list) -> pd.DataFrame:
        """Строит dataframe из информации, которая вышла из функции self.parce,
        содержит в себе 'Имя товара', 'Продавец', 'Цена ₽', 'Оценка', 'Количество оценок', 'Ссылка'"""
        rows = []

        for card in cards:
            link = card.xpath('string(.//a[contains(@class, "product-card__link")]/@href)')
            price = card.xpath('string(.//ins[contains(@class, "price__lower-price")]/text())')
            price = int(re.sub(r'\D', '', price))
            name = card.xpath('normalize-space(.//span[contains(@class, "product-card__name")])').strip('/ ')
            brand = card.xpath('normalize-space(.//span[contains(@class, "product-card__brand")])') or None
            rate = None if not (
                r := card.xpath('normalize-space(.//span[contains(@class, "address-rate-mini")])')) else \
                float(r.replace(',', '.'))
            rate_count = None if not (rc := card.xpath('normalize-space(.//span[contains(@class, "product-card__count")])')) \
                 else rc.split()[0]

            rows.append([name, brand, price, rate, rate_count, link])
        df = pd.DataFrame(rows, columns=['Имя товара', 'Продавец', 'Цена ₽', 'Оценка', 'Количество оценок', 'Ссылка'])
        return df

    def get_cards(self, data: str) -> list:
        """Возвращает список карточек товаров Wildberries, которые содержат всю нужную информацию, для дальнейшего извлечения"""
        tree = html.fromstring(data)
        cards = tree.xpath('.//div[contains(@class, "product-card__wrapper")]')
        return cards

    ### save methods
    def save_to_sql(self, df_queue: queue.Queue) -> None:
        import sqlite3
        conn = sqlite3.connect('database.db', check_same_thread=False)
        while True:
            df, category_name = df_queue.get()
            if df is None:
                break

            try:
                df.to_sql(name=category_name, con=conn)
            except (sqlite3.Error, ValueError) as e:
                print(e)
        conn.close()
