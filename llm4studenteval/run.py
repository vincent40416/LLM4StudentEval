from studenteval import evaluate_folder

import argparse

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='manual to this script')
    parser.add_argument("--input_path", type=str, required=True)
    parser.add_argument("--output_path", type=str, default=None)
    parser.add_argument("--generate_pdf_report", type=bool, default=False)
    args = parser.parse_args()

    evaluate_folder(folder_path=args.input_path,output_path=args.output_path,generate_pdf_report=args.generate_pdf_report)