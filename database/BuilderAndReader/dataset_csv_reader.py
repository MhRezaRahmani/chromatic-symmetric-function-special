import sqlite3
import networkx as nx
import csv

def read_csv_graph6(n =18):
    with open("trees_n"+str(n)+".csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            graph6 = row["graph6"]
            polynomial = row["polynomial"]

            print(graph6)
            print(polynomial)

def read_csv_networkx(n =18):
    with open("trees_n"+str(n)+".csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            T = nx.from_graph6_bytes(row["graph6"].encode("ascii"))

            print(T.number_of_nodes())
            print(T.number_of_edges())