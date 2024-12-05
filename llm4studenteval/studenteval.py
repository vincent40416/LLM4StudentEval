import pandas as pd
import os
from fillpdf import fillpdfs
import json
from tqdm import tqdm

from profile_extractor import read_profiles_from_folder
from utils import llm_evaluation
from prompts import system_prompt_v3__3 as system_prompt

def decompose_response(response):
    sections = response.strip().split('\n\n')

    # Initialize lists to store data
    major = None
    ratings = {}
    summary = None

    # Loop through each line and extract data
    for section in sections:
        lines = section.strip().split('\n')
        if 'Major' in lines[0]:
            major = lines[0].split(': ')[1].split('(')[0]
        if 'Rating' in lines[0]:
            for line in lines[1:]:
                category, score_and_des = line.split(':')[0], line.split(':')[-1]
                category = category.replace('-','').strip()
                score = score_and_des.split('(')[0].strip().split('/')[0]
                try:
                    description = score_and_des.split('(')[1].split(')')[0]
                except:
                    description = ""
                try:
                    score = float(score)
                except ValueError:
                    score = -1
                ratings[category] = score
                ratings[category + "_description"] = description
        elif 'Summary' in lines[0]:
            summary = ' '.join(lines[1:]).strip()

    # Create a dataframe
    df = pd.DataFrame(ratings, index=[0])

    # Add Major column
    df['Major'] = major
    df["Summary"] = summary

    js = df.to_dict(orient='records')[0]
    return js, df

def evaluate_folder(folder_path, output_path, generate_pdf_report):

    save_path = f"{folder_path}/Result" if output_path == None else output_path

    profile_list = read_profiles_from_folder(folder_path)

    for profile in tqdm(profile_list):
        ID = profile["ID"]
        #filtered_profile = {key: profile[key] for key in important_keys} #Yongyu: the filter process has been moved to read_files_in_folder() step
        response = llm_evaluation(system_prompt,profile)
        profile["response"] = response
        parsed_result_js, _ = decompose_response(response)
        profile['parsed_evaluation_result'] = parsed_result_js

        # Yongyu: for personal evaluation result pdf generation:
        pdf_data_dict = {
            'Name':profile['ID']['identity'][0],
            'Application Num':profile['ID']['identity'][1],
        }
        for key in profile['parsed_evaluation_result'].keys():
            pdf_data_dict[key] = profile['parsed_evaluation_result'][key]

        if not os.path.exists(save_path):
            # Create a new directory because it does not exist
            os.makedirs(save_path)

        with open(f'{save_path}/{ID["identity"][1]}.json', 'w') as fp:
            json.dump(profile, fp, indent=4, ensure_ascii=False)
        
        if generate_pdf_report:
            fillpdfs.write_fillable_pdf("evaluation_result_template_v2.pdf", 
                                        f'{save_path}/{ID["identity"][1]}_evaluation_report.pdf', 
                                        pdf_data_dict)

    df_list = []
    for filename in os.listdir(save_path):
        # Construct absolute path to file
        file_path = os.path.join(save_path, filename)
        
        # Check if the current path is a file and not a directory
        if os.path.isfile(file_path) and ".json" in file_path:
            print(f"Found file: {filename}")
            with open(file_path, 'r') as fp:
                data = json.load(fp)
            _ , decomposed_text = decompose_response(data["response"])
            decomposed_text["id"] = data["ID"]["identity"][1]
            decomposed_text["name"] = data["ID"]["identity"][0]
            df_list.append(decomposed_text)


    decomposed_df = pd.concat(df_list, ignore_index=True)
    cols = decomposed_df.columns.tolist()
    cols = cols[-2:] +cols[-4:-2] + cols[:-4]
    decomposed_df = decomposed_df[cols]

    save_csv_path = f'{save_path}/csv_summary'
    if not os.path.exists(save_csv_path):
        # Create a new directory because it does not exist
        os.makedirs(save_csv_path)
    decomposed_df.to_csv(f"{save_csv_path}/summary.csv", index=False)