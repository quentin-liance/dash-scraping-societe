import base64
import io
import os
import random
import time

import constants as csts
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup as bs
from dash import Input, Output, State, dcc, html

# Initialiser l'application Dash
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = dbc.Container(
    [
        html.H1("Application Dash - Prétraitement avec Scraping"),
        dcc.Upload(
            id='upload-data',
            children=html.Div(['Glissez et déposez ou ', html.A('sélectionnez un fichier')]),
            style={
                'width': '100%',
                'height': '60px',
                'lineHeight': '60px',
                'borderWidth': '1px',
                'borderStyle': 'dashed',
                'borderRadius': '5px',
                'textAlign': 'center',
                'margin': '10px'
            },
            multiple=False
        ),
        # html.Div(id='output-data-upload'),
        dcc.Loading(
            id="loading-output",
            type="default",  # Vous pouvez choisir différents types de roue de chargement
            children=html.Div(id="output-data-upload")
            ),
        dbc.Button("Télécharger le fichier modifié", id="download-btn", color="primary", className="mt-3", disabled=True),
        dcc.Download(id="download-dataframe-xlsx"),
    ],
    fluid=True,
)

def preprocess_data(fournisseur):
    print("Starting preprocessing with scraping")

    # Chargement des headers depuis le fichier YAML
    headers_path = os.path.join(os.path.dirname(__file__), 'headers.yml')
    with open(headers_path, "r") as f_headers:
        browser_headers = yaml.safe_load(f_headers)

    # Préparation des données du fournisseur
    fournisseur.columns = [col.upper() for col in fournisseur.columns]
    fournisseur["NOM_FORMATE"] = fournisseur["NOM"].str.strip().str.lower().str.replace(" ", "-")
    fournisseur["SIREN"] = fournisseur["SIREN"].str.zfill(9)
    fournisseur["SIRET"] = fournisseur["SIRET"].str.zfill(14)

    # Génération des URLs
    fournisseur["URL_SIREN"] = csts.SOCIETE_URL + fournisseur["NOM_FORMATE"] + "-" + fournisseur["SIREN"].astype(str) + csts.HTML
    fournisseur["URL_SIRET"] = csts.ETABLISSEMENT_URL + fournisseur["NOM_FORMATE"] + "-" + fournisseur["SIRET"].astype(str) + csts.HTML

    # Fonction de scraping
    def scrape_data(urls, parse_function):
        results = []
        total_iterations = len(urls)
        for i, url in enumerate(urls):
            try:
                browser_name = random.choice(csts.BROWSERS)
                headers = browser_headers[browser_name]
                response = requests.get(url=url, headers=headers)
                print(response.status_code)
                time.sleep(csts.TIME_SLEEP)
                results.append(parse_function(url, response.content))
            except Exception as e:
                print(f"Error processing URL {url}: {e}")
            print(f"Progress: {int((i+1) / total_iterations * 100)}%")
        return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

    # Parsing des noms commerciaux
    def parse_nom_commercial(url, html_content):
        soup = bs(html_content, "html.parser")
        table = soup.find("table", class_="Table identity mt-16")
        return pd.DataFrame([{
            "SIREN": url.split("-")[-1].split(".")[0],
            "NOM_COMMERCIAL": table.find("td", class_="break-word").text,
            "NUMERO_TVA": soup.find("div", id="tva_number").text.strip()
        }])

    # Parsing des adresses
    def parse_adresse(url, html_content):
        soup = bs(html_content, "html.parser")
        adresse = soup.find_all("a", class_="Lien secondaire")[-1].text.strip()
        return pd.DataFrame([{
            "SIRET": url.split("-")[-1].split(".")[0],
            "ADRESSE_ETABLISSEMENT": adresse
        }])

    # Scraping des noms commerciaux et des adresses
    donnees_entreprises = scrape_data(fournisseur["URL_SIREN"].unique(), parse_nom_commercial)
    adresses_etablissements = scrape_data(fournisseur["URL_SIRET"].unique(), parse_adresse)

    # Fusion des résultats
    fournisseur_enrichie = (fournisseur
        .merge(donnees_entreprises, how="left", on="SIREN", validate="m:1")
        .merge(adresses_etablissements, how="left", on="SIRET", validate="1:1")
    )
    
    print("Preprocessing completed.")
    return fournisseur_enrichie

@app.callback(
    [Output("output-data-upload", "children"),
     Output("download-btn", "disabled")],
    Input("upload-data", "contents"),
    State("upload-data", "filename")
)
def update_output(contents, filename):
    if contents is None:
        return html.Div("Veuillez charger un fichier."), True

    print(f"File received: {filename}")

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    fournisseur = pd.read_excel(io=io.BytesIO(decoded), dtype=csts.INPUT_DTYPE)

    # Appliquer le prétraitement simple
    fournisseur_enrichie = preprocess_data(fournisseur)

    download_disabled = False  # Activer le bouton de téléchargement

    return (
        html.Div([
            html.H5(f"Fichier traité : {filename}"),
            dbc.Table.from_dataframe(fournisseur_enrichie.head(), striped=True, bordered=True, hover=True),
        ]), download_disabled
    )

# Callback pour permettre le téléchargement du fichier modifié
@app.callback(
    Output("download-dataframe-xlsx", "data"),
    Input("download-btn", "n_clicks"),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
    prevent_initial_call=True,
)
def download_file(n_clicks, contents, filename):
    if contents is None:
        return None

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    fournisseur = pd.read_excel(io=io.BytesIO(decoded), dtype=csts.INPUT_DTYPE)

    # Appliquer le prétraitement
    fournisseur_enrichie = preprocess_data(fournisseur)

    # Préparer le fichier pour le téléchargement
    return dcc.send_data_frame(fournisseur_enrichie.to_excel, f"modified_{filename}", index=False)

if __name__ == '__main__':
    app.run_server(debug=True, host="0.0.0.0") 