import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AskPage } from '../pages/AskPage';

describe('AskPage Not Found State', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  it('renders initial page header and placeholder', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <AskPage />
      </QueryClientProvider>
    );

    expect(screen.getByRole('heading', { level: 1, name: 'Ask' })).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        'Ask why a decision was made, who owns a system, or what replaced something'
      )
    ).toBeInTheDocument();
  });

  it('displays not found message for unanswerable question', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <AskPage />
      </QueryClientProvider>
    );

    const input = screen.getByPlaceholderText(
      'Ask why a decision was made, who owns a system, or what replaced something'
    );
    const submitBtn = screen.getByRole('button', { name: 'Ask' });

    // Submit unanswerable question
    fireEvent.change(input, {
      target: { value: 'Why did we choose quantum encryption for database backups?' },
    });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText('No answer found in the indexed tickets, notes, and records.')
      ).toBeInTheDocument();
    });

    // Ensure no citations are rendered
    expect(screen.queryByText(/Sources \(/)).not.toBeInTheDocument();
  });
});
