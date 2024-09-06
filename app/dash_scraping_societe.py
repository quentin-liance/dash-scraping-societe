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
        html.Div(id='output-data-upload'),
        dbc.Progress(id="progress-bar", value=0, striped=True, animated=True, className="mt-3"),
        html.Div(id="progress-text", className="mt-3"),
        dbc.Button("Télécharger le fichier modifié", id="download-btn", color="primary", className="mt-3", disabled=True),
        dcc.Download(id="download-dataframe-xlsx"),
    ],
    fluid=True,
)

# Fonction de prétraitement avec scraping pour les noms commerciaux
def preprocess_data(fournisseur):
    print("Starting preprocessing with scraping")

    current_dir = os.path.dirname(__file__)
    headers_path = os.path.join(current_dir, 'headers.yml')

    # Chargement des headers
    with open(headers_path, "r") as f_headers:
        browser_headers = yaml.safe_load(f_headers)

    # Préparation des données
    fournisseur.columns = [col.upper() for col in fournisseur.columns]
    fournisseur["NOM_FORMATE"] = fournisseur["NOM"].str.strip().str.lower().str.replace(" ", "-")
    fournisseur["SIREN"] = fournisseur["SIREN"].str.zfill(9)
    fournisseur["SIRET"] = fournisseur["SIRET"].str.zfill(14)
    fournisseur["URL_SIREN"] = csts.SOCIETE_URL + fournisseur["NOM_FORMATE"] + "-" + fournisseur["SIREN"].astype("string") + csts.HTML
    fournisseur["URL_SIRET"] = (csts.ETABLISSEMENT_URL+ fournisseur["NOM_FORMATE"] + "-" + fournisseur["SIRET"].astype("string") + csts.HTML)

    societe_url = fournisseur["URL_SIREN"].unique().tolist()
    total_iterations = len(societe_url)
    current_iteration = 0

    # Scraping des noms commerciaux
    donnees_entreprises = []
    for url in societe_url:
        try:
            browser_name = random.choice(csts.BROWSERS)
            headers = browser_headers[browser_name]
            response = requests.get(url=url, headers=headers)
            time.sleep(csts.TIME_SLEEP)
            html = response.content
            contenu_page = bs(html, "html.parser")
            contenu_page = contenu_page.find_all(name="table", class_="Table identity mt-16")[0]
            numero_siren = url.split("-")[-1].split(".")[0]
            nom_commercial = contenu_page.find(name="td", class_="break-word").text
            numero_tva = contenu_page.find(name="div", id="tva_number").text.replace("\n", "")
            donnees_entreprise = pd.DataFrame([{
                "SIREN": numero_siren,
                "NOM_COMMERCIAL": nom_commercial,
                "NUMERO_TVA": numero_tva,
            }])
            donnees_entreprises.append(donnees_entreprise)
        except Exception as e:
            print(f"Error processing URL {url}: {e}")
            continue

        current_iteration += 1
        progress_percentage = int((current_iteration / total_iterations) * 100)
        print(f"Progress: {progress_percentage}%")

    donnees_entreprises = pd.concat(objs=donnees_entreprises, axis=0, ignore_index=True)
    print("Scraping des noms commerciaux terminé.")

    # Scraping de l'adresse des établissements
    etablissement_url = fournisseur["URL_SIRET"].unique().tolist()
    total_iterations = len(etablissement_url)
    current_iteration = 0

    adresses_etablissements = []
    for url in etablissement_url:
        try:
            browser_name = random.choice(csts.BROWSERS)
            headers = browser_headers[browser_name]
            response = requests.get(url=url, headers=headers)
            time.sleep(csts.TIME_SLEEP)
            html = response.content
            contenu_page = bs(html, "html.parser")
            contenu_page = contenu_page.find_all(name="a", class_="Lien secondaire")[-1]
            numero_siret = url.split("-")[-1].split(".")[0]
            adresse_etablissement = contenu_page.text.strip()
            adresse_etablissement = pd.DataFrame([{
                "SIRET": numero_siret,
                "ADRESSE_ETABLISSEMENT": adresse_etablissement,
                }])
            adresses_etablissements.append(adresse_etablissement)

        except Exception as e:
            print(f"Error processing URL {url}: {e}")
            continue

        current_iteration += 1
        progress_percentage = int((current_iteration / total_iterations) * 100)
        print(f"Progress: {progress_percentage}%")
    adresses_etablissements = pd.concat(objs=adresses_etablissements, axis=0, ignore_index=True)
    print("Scraping de l'adresse des établissements terminé.")

    # Rassemblement
    fournisseur_enrichie = (fournisseur
        .merge(
            right=donnees_entreprises,
            how="left",   
            on="SIREN",
            validate="m:1",
            )
        .merge(
            right=adresses_etablissements,
            how="left",
            on="SIRET",
            validate="1:1",
            )
        )
    return fournisseur_enrichie

@app.callback(
    [Output("output-data-upload", "children"),
     Output("progress-bar", "value"),
     Output("progress-bar", "label"),
     Output("progress-text", "children"),
     Output("download-btn", "disabled")],
    Input("upload-data", "contents"),
    State("upload-data", "filename")
)
def update_output(contents, filename):
    if contents is None:
        return html.Div("Veuillez charger un fichier."), 0, "", "En attente du fichier...", True

    print(f"File received: {filename}")

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    fournisseur = pd.read_excel(io=io.BytesIO(decoded), dtype=csts.INPUT_DTYPE)

    # Appliquer le prétraitement simple
    fournisseur_enrichie = preprocess_data(fournisseur)

    # Mise à jour finale de la progression
    value = 100  # Progression à 100% après traitement
    label = "100%"
    text = "Prétraitement terminé"
    download_disabled = False  # Activer le bouton de téléchargement

    return (
        html.Div([
            html.H5(f"Fichier traité : {filename}"),
            dbc.Table.from_dataframe(fournisseur_enrichie.head(), striped=True, bordered=True, hover=True),
        ]),
        value, label, text, download_disabled
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