import os

MCI_PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

if __name__ == "__main__":
    print(MCI_PROJECT_DIR)
