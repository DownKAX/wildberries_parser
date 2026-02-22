import tkinter as tk
import threading
import queue

import pandas as pd

from parser_wb import SeleniumUtility
import json

from typing import TypeAlias, Union

CategoryTree: TypeAlias = dict[str, Union[str, "CategoryTree"]]


class TkinterAppGUI:
    def __init__(self):
        ### base init
        self.root = tk.Tk()
        self.root.title("WB Parser")
        self.root.geometry("900x400")

        self.parser = SeleniumUtility()
        self.path_to_json_categories = 'categories.json'

        ### Frames
        self.right_frame = tk.Frame(self.root)
        self.right_frame.pack(side='right', padx=15, pady=5)

        self.right_btn_frame = tk.Frame(self.root)
        self.right_btn_frame.pack(side='right', padx=10)

        ### Создаём listbox, в котором будем хранить элементы(категории товаров), выбранные пользователем для парсинга
        self.listbox = tk.Listbox(self.right_frame, width=100, height=20)
        self.listbox.pack(side='right', padx=0, pady=0)

        ### Кнопки

        # Удаление выделенного элемента из listbox
        self.del_btn = tk.Button(self.right_btn_frame, text='Удалить', command=lambda: self.listbox.delete(self.listbox.curselection()))
        self.del_btn.pack(pady=5)

        # Удаление всех элементов из listbox
        self.del_all_btn = tk.Button(self.right_btn_frame, text='Удалить всё', command=lambda: self.listbox.delete(0, tk.END))
        self.del_all_btn.pack(pady=5)


        # Обновить категории
        self.update_btn = tk.Button(self.right_btn_frame, text='Обновить категории', command=self.update_categories_and_rebuild_app)
        self.update_btn.pack(pady=5)

        # Начать парсинг
        self.start_parse = tk.Button(self.right_btn_frame, text='Начать парсинг', command=lambda: threading.Thread(target=self.parse_selected_categories,
                                                                                                                   daemon=True).start())
        self.start_parse.pack(pady=5)

        ### Все категории в виде выпадающего меню
        self.category_links = {} # сохраняем название-из-lisbox:ссылка
        self.main_menu = tk.Menu(self.root)
        self.root.config(menu=self.main_menu)

        with open(self.path_to_json_categories, 'r', encoding='utf-8') as file:
            data = json.load(file)

        for category in data:
            # Добавляем все основные категории как элементы меню
            category_menu_element: tk.Menu = tk.Menu(self.main_menu, tearoff=0)
            self.main_menu.add_cascade(label=category, menu=category_menu_element)

            # item - элемент(ы)(подкатегория) самой старшей категории в виде:
            # либо, например, ('Костюмы', '/catalog/zhenshchinam/odezhda/kostyumy')
            # либо ('Белье', {'Аксессуары': '/catalog/zhenshchinam/bele/aksessuary', ... ... ...
            if isinstance(data[category], dict):
                item = data[category].items()
            elif isinstance(data[category], str):
                item = ((category, data[category]),)
            else:
                continue

            # Устанавливаем элементы выпадающего меню для текущей категории с учётом наличия вложенности
            self.set_elements_recursive(item, category, category_menu_element)




        self.root.mainloop()

    def update_categories_and_rebuild_app(self) -> None:
        """
        Использует parser, чтобы прочитать внешний json и построить собственный с вложенностями;
        Перезапускает приложение, чтобы перестроить UI с учётом обновлений
        """
        self.parser.build_json_with_categories()
        self.root.destroy()
        TkinterAppGUI()

    def set_elements_recursive(self, category_elements: CategoryTree | tuple[str, str], category_name: str, menu: tk.Menu):
        """Строит сверху приложения меню с выпадающими элементами - кнопками, которые добавляют в listbox название категории
        или элемент, при наведении на который выходят ещё элементы, с такими же элементами(учёт вложенности категорий)"""
        for subcategory in category_elements:
            subcategory_name: str = subcategory[0]
            link_or_elements: str | CategoryTree = subcategory[1]

            # Если элемент простой(без вложенности), то просто добавляем его как кликабельный элемент, который при нажатии добавляет
            # категорию в listbox
            if isinstance(link_or_elements, str):
                listbox_content = f"{category_name}-{subcategory[0]}"
                self.category_links[listbox_content] = self.parser.wb_url + link_or_elements #бред
                menu.add_command(label=subcategory_name, command=lambda content=listbox_content: self.listbox.insert(tk.END, content))

            # Если элемент с вложенностью, то добавляем его как элемент, при наведении на него выпадают его элементы
            # с произвольной вложенностью
            elif isinstance(link_or_elements, dict):
                sub_menu = tk.Menu(menu, tearoff=0)
                menu.add_cascade(label=subcategory_name, menu=sub_menu)
                self.set_elements_recursive(link_or_elements.items(), menu=sub_menu, category_name=f"{category_name}-{subcategory_name}")

    def parse_selected_categories(self):
        """Использует webdriver selenium, чтобы поочерёдно посетить страницы, промотать их до определённого лимита,
        собирает всю информацию в queue и сохраняет(пока что только в sql)"""
        driver = self.parser.get_driver()
        data_queue = queue.Queue()

        # Берём все элементы, которые добавлены пользователем в listbox(с помощью выпадающего меню)
        # Сохраняем результат парсинга в queue
        for category_name in set(self.listbox.get(0, tk.END)):
            url = self.category_links[category_name]
            data = self.parser.parse(url=url, driver=driver)
            df: pd.DataFrame = self.parser.extract_data_from_html(data)
            data_queue.put((df, category_name))

        data_queue.put((None, None))
        self.parser.save_to_sql(df_queue=data_queue)
        driver.quit()




if __name__ == '__main__':
    TkinterAppGUI()