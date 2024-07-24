import os
from eden import EdenClient

client = EdenClient()


# client.upload("https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/kyuuefmnf56cnot8mqug.jpg")

files_dir = "/Users/gene/bin/___datasets/images/marzipan"


files = os.listdir(files_dir)
# training_urls = [client.upload(os.path.join(files_dir, f))['url'] for f in files]
training_urls = ['https://dtut5r9j4w7j4.cloudfront.net/2277f9e74da21857b4e1314b9d257d5bcb028cc0607c91b9a751bafa930f9451.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/40f03d9e817866de6ab4b731a0c28484f85fee9c18eb3f1ce8ccbbfc94d29bbb.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/be7cb5ac43af3793948f8f0b23abaa4da3184471d61a840e0048ccb360de9bbb.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/f2bdd033c5721716430b3cfbd02caba545628e41a737ac7072c88c883b9d1c84.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/c375a9364dca56769a38fbb2dabeee7e8b70d55af20f72ad08ce85100b0d20df.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/a1cc987ae15500b61fa872de5ad59990c4646b2652585e14a34b5181353ecbff.jpg']
print(training_urls)

training_urls = ['https://dtut5r9j4w7j4.cloudfront.net/7245e07e13d14d36a79f8343e922bf2bcbeaa443bab7c523e1a80cec6a8b5c57.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/5f261045f410ec34a8588dc1fc3b1ed7715d0b8a2ab8e6adc59ba2684a01a4d9.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/798f53c7bb659739b0193788a8c7b8d1da716fb3cc18c78cde3b6b17b143df61.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/1d1e3cbbdf50c082eed806591ced06a262873ebc6a0b18c5c03c35ddd105bd74.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/a9624f8166c061e7bc94b1b9bb01e94fe6e6c61773e8a230c567d37e045cac9a.jpg', 'https://dtut5r9j4w7j4.cloudfront.net/464a9cbaeec6ba7c5f47ec8ff7f6d0f6eaf424e6ebfa4e2361c2b0c3192a7d5a.png', 'https://dtut5r9j4w7j4.cloudfront.net/b25dec2158cf62394ecacc20da75507ebc6ca9e2853145a69b8626e38291ea86.jpg']

# result = client.create("lora_trainer", {
#     "name": "gene",
#     "lora_training_urls": training_urls,
#     "sd_model_version": "sdxl",
#     "concept_mode": "face",
#     "max_train_steps": 300
# })
# print(result)
result = client.create("lora_trainer", {
    "name": "gene",
    "lora_training_urls": training_urls,
    "sd_model_version": "sd15",
    "concept_mode": "face",
    "max_train_steps": 800
})

print(result)
# print(result)

# # print(config)
# # response = eden_client.train(config)
# # print(response)

