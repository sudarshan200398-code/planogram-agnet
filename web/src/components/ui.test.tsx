import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { CheckIcon } from "./icons";
import { Badge, Button, Card, Chip, EmptyState, ErrorState, IconButton, Skeleton } from "./ui";

it("renders the component set without accessibility violations", async () => {
  const { container } = render(
    <main>
      <Button>Find</Button>
      <IconButton label="Search by voice">
        <CheckIcon />
      </IconButton>
      <Chip selected>Bakery</Chip>
      <Badge tone="ok" icon={<CheckIcon />}>
        In stock · 12
      </Badge>
      <Card>
        <h2>Card</h2>
      </Card>
      <Skeleton />
      <EmptyState title="No results">Try another word.</EmptyState>
      <ErrorState title="Something went wrong" message="Please try again." requestId="abc-123" onRetry={() => {}} />
    </main>,
  );
  expect(await axe(container)).toHaveNoViolations();
});

it("the axe check really catches problems (an unlabelled button fails)", async () => {
  const { container } = render(
    <button type="button">
      <CheckIcon />
    </button>,
  );
  const results = await axe(container);
  expect(() => expect(results).toHaveNoViolations()).toThrow(/discernible text/i);
});

it("names icon-only buttons and reports chip selection", () => {
  render(
    <>
      <IconButton label="Clear search">x</IconButton>
      <Chip selected={false}>Dairy</Chip>
    </>,
  );
  expect(screen.getByRole("button", { name: "Clear search" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Dairy" })).toHaveAttribute("aria-pressed", "false");
});

it("shows the request id only as a small reference, and retries", async () => {
  const onRetry = vi.fn();
  render(<ErrorState title="Store is busy" message="Try again shortly." requestId="req-42" onRetry={onRetry} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Reference: req-42");
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(onRetry).toHaveBeenCalledOnce();
});
