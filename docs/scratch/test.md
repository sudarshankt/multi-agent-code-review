## All
uv run pytest tests/unit/ -v

uv run --with pytest-asyncio pytest tests/unit/ -v

uv run --with pytest-asyncio pytest tests/unit/test_security_agent.py -v

## Integration
# Ensure ANTHROPIC_API_KEY is set, then:
uv run pytest tests/integration/test_security_agent.py -v -s

The -s flag is important here — it lets you see pytest.fail(...) diagnostic output with actual finding titles if something goes wrong.



[
	{
		"name": "deepseek",
		"vendor": "customendpoint",
		"apiKey": "${input:chat.lm.secret.7b1f8878}",
		"apiType": "chat-completions",
		"models": [
			{
				"id": "deepseek-v4-pro",
				"name": "deepseek/deepseek-v4-pro",
				"url": "http://api.deepseek.com",
				"toolCalling": true,
				"vision": true,
				"maxInputTokens": 628000,
				"maxOutputTokens": 384000
			}
		]
	}
]