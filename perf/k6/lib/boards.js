// Model-free boards for the wave runs (spec 0057): rule checks only, so no model is called.

const edge = (id, source, target) => ({ id, source, source_handle: id === 'e1' ? 'out' : 'safe', target })

export const EASY_1 = {
  level_id: 'easy-1',
  board: {
    nodes: [
      { id: 'in', kind: 'incoming', config: {} },
      { id: 'wf', kind: 'word_filter', config: { custom_words: ['ignore previous', 'admin password', 'secret key'] } },
      { id: 'len', kind: 'length_limit', config: { max_chars: 600 } },
      { id: 'ast', kind: 'assistant', config: {} }
    ],
    edges: [edge('e1', 'in', 'wf'), edge('e2', 'wf', 'len'), edge('e3', 'len', 'ast')]
  }
}

export const EASY_2 = {
  level_id: 'easy-2',
  board: {
    nodes: [
      { id: 'in', kind: 'incoming', config: {} },
      { id: 'tc', kind: 'text_cleanup', config: {} },
      { id: 'wf', kind: 'word_filter', config: { custom_words: ['ignore previous'] } },
      { id: 'ast', kind: 'assistant', config: {} }
    ],
    edges: [edge('e1', 'in', 'tc'), edge('e2', 'tc', 'wf'), edge('e3', 'wf', 'ast')]
  }
}

export const BOARDS = [EASY_1, EASY_2]

/** A synthetic sign-in that can never belong to a real player. */
export function testUser(vu, iteration) {
  return { email: `k6+${vu}-${iteration}@example.invalid`, password: 'NotAPassw0rd' }
}
