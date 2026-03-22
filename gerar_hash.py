import os
from werkzeug.security import generate_password_hash

def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    limpar_tela()
    print("="*50)
    print("      GERADOR DE SENHAS - ARCSYS PAINEL")
    print("="*50)
    print("Este script gera o código (hash) para o Supabase.\n")

    senha_plana = input(">> Digite a nova senha: ")

    if not senha_plana:
        print("Erro: A senha não pode ser vazia!")
        return

    # Gera o hash usando o padrão do Werkzeug (Scrypt)
    # É exatamente o mesmo método que seu site usa.
    senha_hash = generate_password_hash(senha_plana)

    print("\n" + "="*50)
    print("SUCESSO! Copie o código abaixo para o Supabase:")
    print("="*50)
    print(f"\n{senha_hash}\n")
    print("="*50)
    
    input("\nPressione ENTER para sair...")

if __name__ == "__main__":
    main()