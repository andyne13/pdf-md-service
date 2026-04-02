from openai import OpenAI                                                                                                                                          
client = OpenAI(
    base_url="https://chat.lucie.ovh.linagora.com/v1/",
    api_key="sk-Ch1PFCNjD92T0kj_k4Pa0Q",                                                                                                                           
)
resp = client.chat.completions.create(
    model="Qwen2.5-VL-7B-Instruct",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)

