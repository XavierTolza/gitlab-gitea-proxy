import argparse
import requests
import sys


def get_headers(token):
    """Retourne les en-têtes nécessaires pour l'authentification."""
    return {"Authorization": f"token {token}", "Accept": "application/json"}


def get_all_organizations(base_url, headers):
    """Récupère la liste de toutes les organisations."""
    url = f"{base_url}/orgs"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(
            f"Erreur lors de la récupération des organisations: {response.status_code}"
        )
        return []


def get_org_repos(base_url, headers, org_name):
    """Récupère la liste des dépôts pour une organisation spécifique."""
    url = f"{base_url}/orgs/{org_name}/repos"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(
            f"Erreur lors de la récupération des dépôts pour l'organisation {org_name}: {response.status_code}"
        )
        return []


def get_current_user_repos(base_url, headers):
    """Récupère la liste des dépôts de l'utilisateur authentifié."""
    url = f"{base_url}/user/repos"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(
            f"Erreur lors de la récupération des dépôts de l'utilisateur: {response.status_code}"
        )
        return []


def delete_repository(base_url, headers, owner, repo_name):
    """Supprime un dépôt spécifique."""
    url = f"{base_url}/repos/{owner}/{repo_name}"
    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        print(f"  [SUCCÈS] Dépôt supprimé : {owner}/{repo_name}")
    else:
        print(
            f"  [ÉCHEC] Impossible de supprimer le dépôt {owner}/{repo_name} (Code: {response.status_code})"
        )


def delete_organization(base_url, headers, org_name):
    """Supprime une organisation spécifique."""
    url = f"{base_url}/orgs/{org_name}"
    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        print(f"[SUCCÈS] Organisation supprimée : {org_name}")
    else:
        print(
            f"[ÉCHEC] Impossible de supprimer l'organisation {org_name} (Code: {response.status_code})"
        )


def main():
    parser = argparse.ArgumentParser(
        description="CLI pour supprimer toutes les organisations, tous leurs dépôts, et les dépôts de l'utilisateur actuel sur Gitea."
    )
    parser.add_argument(
        "--url",
        required=True,
        help="L'URL de base de l'API (ex: https://gitea.example.com/api/v1)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Token d'accès personnel avec les droits d'administrateur",
    )

    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    headers = get_headers(args.token)

    print("--- Démarrage du nettoyage de l'instance ---")

    # ==========================================
    # Étape 1 : Nettoyage des dépôts de l'utilisateur
    # ==========================================
    print("\n[Étape 1] Recherche des dépôts de l'utilisateur actuel...")
    user_repos = get_current_user_repos(base_url, headers)

    if not user_repos:
        print("Aucun dépôt personnel trouvé.")
    else:
        print(f"{len(user_repos)} dépôt(s) personnel(s) trouvé(s).")
        for repo in user_repos:
            repo_name = repo.get("name")
            # L'API Gitea renvoie les infos du propriétaire dans l'objet "owner"
            owner_info = repo.get("owner", {})
            owner_name = owner_info.get("login") or owner_info.get("username")

            if owner_name and repo_name:
                delete_repository(base_url, headers, owner_name, repo_name)

    # ==========================================
    # Étape 2 : Nettoyage des organisations
    # ==========================================
    print("\n[Étape 2] Recherche des organisations...")
    orgs = get_all_organizations(base_url, headers)

    if not orgs:
        print("Aucune organisation trouvée.")
    else:
        print(f"{len(orgs)} organisation(s) trouvée(s).")
        for org in orgs:
            org_name = org.get("username") or org.get("name")
            print(f"\nTraitement de l'organisation : {org_name}")

            # Récupération et suppression des dépôts de l'organisation
            repos = get_org_repos(base_url, headers, org_name)
            for repo in repos:
                repo_name = repo.get("name")
                delete_repository(base_url, headers, org_name, repo_name)

            # Suppression de l'organisation
            delete_organization(base_url, headers, org_name)

    print("\n--- Nettoyage terminé ---")


if __name__ == "__main__":
    main()
