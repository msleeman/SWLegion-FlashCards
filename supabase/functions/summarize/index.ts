import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS })

  try {
    const { definition, name } = await req.json()
    if (!definition) return new Response(JSON.stringify({ error: 'No definition' }), { status: 400, headers: CORS })

    const apiKey = Deno.env.get('ANTHROPIC_API_KEY')
    if (!apiKey) return new Response(JSON.stringify({ error: 'API key not configured' }), { status: 500, headers: CORS })

    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 120,
        messages: [{
          role: 'user',
          content: `Summarize this Star Wars Legion keyword rule in 1–2 short sentences. Focus only on what it does in gameplay. No intro phrases like "This rule" or "The keyword". Keep it under 150 characters if possible.

Keyword: ${name}
Rule: ${definition}

Summary:`,
        }],
      }),
    })

    const data = await resp.json()
    const summary = data.content?.[0]?.text?.trim() ?? ''
    if (!summary) throw new Error('Empty response from AI')

    return new Response(JSON.stringify({ summary }), {
      headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }
})
