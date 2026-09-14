import java.util.*;
import java.math.BigInteger;

public class TreeChromaticSpecialFunction {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int k = sc.nextInt();

        List<Integer>[] tree1Edges = new List[n-1];
        for (int i = 0; i < n-1; i++) {
            tree1Edges[i] = new ArrayList<>();
            tree1Edges[i].add(sc.nextInt());
            tree1Edges[i].add(sc.nextInt());
        }

        List<Integer>[] tree2Edges = new List[n-1];
        for (int i = 0; i < n-1; i++) {
            tree2Edges[i] = new ArrayList<>();
            tree2Edges[i].add(sc.nextInt());
            tree2Edges[i].add(sc.nextInt());
        }

        List<Integer>[] adj1 = new List[n];
        for (int i = 0; i < n; i++) {
            adj1[i] = new ArrayList<>();
        }
        for (List<Integer> edge : tree1Edges) {
            int u = edge.get(0);
            int v = edge.get(1);
            adj1[u].add(v);
            adj1[v].add(u);
        }

        List<Integer>[] adj2 = new List[n];
        for (int i = 0; i < n; i++) {
            adj2[i] = new ArrayList<>();
        }
        for (List<Integer> edge : tree2Edges) {
            int u = edge.get(0);
            int v = edge.get(1);
            adj2[u].add(v);
            adj2[v].add(u);
        }

        List<List<Integer>> children1 = buildTreeStructure(adj1, n);
        List<List<Integer>> children2 = buildTreeStructure(adj2, n);

        int maxDegree = n * k;
        BigInteger[] poly1 = computeTreePolynomial(children1, n, k, maxDegree);
        BigInteger[] poly2 = computeTreePolynomial(children2, n, k, maxDegree);

        System.out.println("Tree 1 Polynomial:");
        printPolynomial(poly1);
        System.out.println("Tree 2 Polynomial:");
        printPolynomial(poly2);

        boolean equal = true;
        for (int s = 0; s <= maxDegree; s++) {
            if (!poly1[s].equals(poly2[s])) {
                equal = false;
                break;
            }
        }
        if (equal) {
            System.out.println("The special functions are equal.");
        } else {
            System.out.println("The special functions are not equal.");
        }
    }

    private static List<List<Integer>> buildTreeStructure(List<Integer>[] adj, int n) {
        List<List<Integer>> children = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            children.add(new ArrayList<>());
        }
        Queue<Integer> queue = new LinkedList<>();
        boolean[] visited = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        queue.add(0);
        visited[0] = true;
        while (!queue.isEmpty()) {
            int u = queue.poll();
            for (int v : adj[u]) {
                if (v == parent[u]) continue;
                visited[v] = true;
                parent[v] = u;
                children.get(u).add(v);
                queue.add(v);
            }
        }
        return children;
    }

    private static BigInteger[] computeTreePolynomial(List<List<Integer>> children, int n, int k, int maxDegree) {
        BigInteger[][][] dp = new BigInteger[n][k+1][maxDegree+1];
        for (int u = 0; u < n; u++) {
            for (int c = 0; c <= k; c++) {
                for (int s = 0; s <= maxDegree; s++) {
                    dp[u][c][s] = BigInteger.ZERO;
                }
            }
        }
        int[] order = getDFSOrder(children, 0);
        for (int i = order.length - 1; i >= 0; i--) {
            int u = order[i];
            if (children.get(u).isEmpty()) {
                for (int c = 0; c <= k; c++) {
                    if (c <= maxDegree) {
                        dp[u][c][c] = BigInteger.ONE;
                    }
                }
            } else {
                for (int c = 0; c <= k; c++) {
                    BigInteger[] poly = new BigInteger[maxDegree+1];
                    Arrays.fill(poly, BigInteger.ZERO);
                    poly[0] = BigInteger.ONE;
                    for (int v : children.get(u)) {
                        BigInteger[] childPoly = new BigInteger[maxDegree+1];
                        Arrays.fill(childPoly, BigInteger.ZERO);
                        for (int cv = 0; cv <= k; cv++) {
                            if (cv == c) continue;
                            for (int s = 0; s <= maxDegree; s++) {
                                childPoly[s] = childPoly[s].add(dp[v][cv][s]);
                            }
                        }
                        BigInteger[] newPoly = new BigInteger[maxDegree+1];
                        Arrays.fill(newPoly, BigInteger.ZERO);
                        for (int s1 = 0; s1 <= maxDegree; s1++) {
                            if (poly[s1].equals(BigInteger.ZERO)) continue;
                            for (int s2 = 0; s2 <= maxDegree; s2++) {
                                if (s1 + s2 > maxDegree) break;
                                if (childPoly[s2].equals(BigInteger.ZERO)) continue;
                                newPoly[s1+s2] = newPoly[s1+s2].add(poly[s1].multiply(childPoly[s2]));
                            }
                        }
                        poly = newPoly;
                    }
                    for (int s = 0; s <= maxDegree; s++) {
                        if (s + c <= maxDegree) {
                            dp[u][c][s+c] = dp[u][c][s+c].add(poly[s]);
                        }
                    }
                }
            }
        }
        BigInteger[] total = new BigInteger[maxDegree+1];
        Arrays.fill(total, BigInteger.ZERO);
        for (int c = 0; c <= k; c++) {
            for (int s = 0; s <= maxDegree; s++) {
                total[s] = total[s].add(dp[0][c][s]);
            }
        }
        return total;
    }

    private static int[] getDFSOrder(List<List<Integer>> children, int root) {
        List<Integer> orderList = new ArrayList<>();
        Stack<Integer> stack = new Stack<>();
        stack.push(root);
        while (!stack.isEmpty()) {
            int u = stack.pop();
            orderList.add(u);
            for (int i = children.get(u).size() - 1; i >= 0; i--) {
                stack.push(children.get(u).get(i));
            }
        }
        int[] order = new int[orderList.size()];
        for (int i = 0; i < orderList.size(); i++) {
            order[i] = orderList.get(i);
        }
        return order;
    }

    private static void printPolynomial(BigInteger[] poly) {
        boolean first = true;
        for (int s = 0; s < poly.length; s++) {
            if (!poly[s].equals(BigInteger.ZERO)) {
                if (!first) {
                    System.out.print(" + ");
                }
                System.out.print(poly[s] + "q^" + s);
                first = false;
            }
        }
        if (first) {
            System.out.println("0");
        } else {
            System.out.println();
        }
    }
}